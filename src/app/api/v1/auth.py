from fastapi import APIRouter

router = APIRouter()


@router.post("/register", status_code=201)
async def register():
    # TODO: implement via auth_service.register()
    raise NotImplementedError


@router.post("/login")
async def login():
    # TODO: implement via auth_service.login()
    raise NotImplementedError


@router.post("/oauth/google")
async def oauth_google():
    # TODO: implement via auth_service.oauth_login("google", code)
    raise NotImplementedError


@router.post("/oauth/microsoft")
async def oauth_microsoft():
    # TODO: implement via auth_service.oauth_login("microsoft", code)
    raise NotImplementedError


@router.post("/oauth/apple")
async def oauth_apple():
    # TODO: implement via auth_service.oauth_login("apple", code)
    raise NotImplementedError


@router.post("/refresh")
async def refresh_token():
    # TODO: implement via auth_service.refresh_tokens()
    raise NotImplementedError


@router.post("/logout")
async def logout():
    # TODO: implement via auth_service.logout()
    raise NotImplementedError


@router.post("/forgot-password")
async def forgot_password():
    # TODO: implement via auth_service.forgot_password()
    raise NotImplementedError


@router.post("/reset-password")
async def reset_password():
    # TODO: implement via auth_service.reset_password()
    raise NotImplementedError


@router.post("/verify-email")
async def verify_email():
    # TODO: implement via auth_service.verify_email()
    raise NotImplementedError
