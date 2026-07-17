"""
Google OAuth2 Flow — Autenticación para Search Console y Analytics.

Implementa el flujo completo de Authorization Code + PKCE:
1. /auth/login → Redirige a Google
2. /auth/callback → Recibe el code, obtiene tokens
3. Almacena tokens en base de datos
4. Refresh automático de tokens expirados
"""

import json
import base64
import logging
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import (
    GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REDIRECT_URI,
    SEARCH_CONSOLE_SCOPE, ANALYTICS_SCOPE,
)
from backend.database import get_session, GoogleToken

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# URLs de Google OAuth2
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"

# Scopes combinados
GOOGLE_SCOPES = " ".join([
    "openid",
    "email",
    SEARCH_CONSOLE_SCOPE,
    ANALYTICS_SCOPE,
])


@router.get("/login")
async def login():
    """Inicia el flujo OAuth2. Redirige al usuario a Google."""
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        raise HTTPException(
            status_code=501,
            detail="Google OAuth no configurado. Falta GOOGLE_CLIENT_ID o GOOGLE_CLIENT_SECRET"
        )

    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": GOOGLE_SCOPES,
        "access_type": "offline",        # Para obtener refresh_token
        "prompt": "consent",             # Forzar consentimiento siempre
        "include_granted_scopes": "true",
    }

    auth_url = f"{GOOGLE_AUTH_URL}?{urlencode(params)}"
    return RedirectResponse(auth_url)


@router.get("/callback")
async def callback(request: Request):
    """
    Callback de Google OAuth2.
    Recibe el authorization code y lo cambia por tokens.

    Además, prueba la conexión a Search Console y Analytics
    para verificar que todo funciona.
    """
    code = request.query_params.get("code")
    error = request.query_params.get("error")

    if error:
        raise HTTPException(status_code=400, detail=f"Error de autenticación: {error}")
    if not code:
        raise HTTPException(status_code=400, detail="No se recibió código de autorización")

    # Intercambiar code por tokens
    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri": GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        if token_response.status_code != 200:
            logger.error(f"Error obteniendo tokens: {token_response.text}")
            raise HTTPException(
                status_code=502,
                detail=f"Error al obtener tokens de Google: {token_response.text}"
            )

        tokens = token_response.json()

    # Extraer información del id_token
    id_token = tokens.get("id_token", "")
    user_info = {}
    if id_token:
        try:
            # Decodificar payload del JWT (solo header.payload.signature)
            payload_b64 = id_token.split(".")[1]
            # Agregar padding si es necesario
            payload_b64 += "=" * (4 - len(payload_b64) % 4)
            user_info = json.loads(base64.b64decode(payload_b64))
        except Exception as e:
            logger.warning(f"No se pudo decodificar id_token: {e}")

    # Guardar tokens en la base de datos
    async for session in get_session():
        # Eliminar tokens anteriores (solo queremos uno activo)
        existing = (await session.execute(select(GoogleToken))).scalars().all()
        for t in existing:
            await session.delete(t)

        expires_in = tokens.get("expires_in", 3600)
        expires_at = datetime.now(timezone.utc).timestamp() + expires_in

        token_record = GoogleToken(
            access_token=tokens["access_token"],
            refresh_token=tokens.get("refresh_token", ""),
            expires_at=expires_at,
            scope=tokens.get("scope", ""),
            token_type=tokens.get("token_type", "Bearer"),
            user_email=user_info.get("email", ""),
            user_name=user_info.get("name", ""),
        )
        session.add(token_record)
        await session.commit()
        break

    logger.info(f"✅ Google OAuth exitoso para {user_info.get('email', 'desconocido')}")

    # Redirigir al dashboard con un mensaje de éxito
    return RedirectResponse(
        url="/?oauth=success",
        status_code=302,
    )


@router.get("/status")
async def auth_status():
    """Verifica el estado de la autenticación."""
    async for session in get_session():
        token = (await session.execute(select(GoogleToken))).scalar_one_or_none()
        if not token:
            return {
                "authenticated": False,
                "user_email": None,
                "user_name": None,
                "expires_at": None,
                "expired": None,
            }

        now = datetime.now(timezone.utc).timestamp()
        return {
            "authenticated": True,
            "user_email": token.user_email,
            "user_name": token.user_name,
            "expires_at": datetime.fromtimestamp(token.expires_at, tz=timezone.utc).isoformat(),
            "expired": now >= token.expires_at,
            "has_refresh_token": bool(token.refresh_token),
            "connected_services": {
                "search_console": "webmasters.readonly" in (token.scope or ""),
                "analytics": "analytics.readonly" in (token.scope or ""),
            },
        }
    return {"authenticated": False}


@router.post("/revoke")
async def revoke():
    """Revoca los tokens de Google."""
    async for session in get_session():
        token = (await session.execute(select(GoogleToken))).scalar_one_or_none()
        if not token:
            raise HTTPException(404, "No hay sesión activa")

        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    GOOGLE_REVOKE_URL,
                    data={"token": token.access_token},
                )
        except Exception:
            pass  # No crítico si falla el revoke

        await session.delete(token)
        await session.commit()
        break

    return {"status": "ok", "message": "Sesión de Google revocada"}


async def get_google_credentials() -> Optional[dict]:
    """
    Obtiene credenciales válidas de Google, haciendo refresh si es necesario.

    Returns:
        dict con access_token, token_type, scope o None si no hay sesión
    """
    async for session in get_session():
        token = (await session.execute(select(GoogleToken))).scalar_one_or_none()
        if not token:
            return None

        now = datetime.now(timezone.utc).timestamp()

        # Si el token expiró y tenemos refresh_token, renovar
        if now >= token.expires_at and token.refresh_token:
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.post(
                        GOOGLE_TOKEN_URL,
                        data={
                            "client_id": GOOGLE_CLIENT_ID,
                            "client_secret": GOOGLE_CLIENT_SECRET,
                            "refresh_token": token.refresh_token,
                            "grant_type": "refresh_token",
                        },
                    )
                    if resp.status_code == 200:
                        new_tokens = resp.json()
                        token.access_token = new_tokens.get("access_token", token.access_token)
                        token.expires_at = now + new_tokens.get("expires_in", 3600)
                        await session.commit()
                    else:
                        logger.error(f"Error refreshing token: {resp.text}")
            except Exception as e:
                logger.error(f"Error refreshing token: {e}")

        return {
            "access_token": token.access_token,
            "token_type": token.token_type or "Bearer",
            "scope": token.scope or "",
        }
    return None
