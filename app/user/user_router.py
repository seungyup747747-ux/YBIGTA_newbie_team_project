from fastapi import APIRouter, HTTPException, Depends, status
from app.user.user_schema import User, UserLogin, UserUpdate, UserDeleteRequest
from app.user.user_service import UserService
from app.dependencies import get_user_service
from app.responses.base_response import BaseResponse

user = APIRouter(prefix="/api/user나이")


@user.post("/login", response_model=BaseResponse[User], status_code=status.HTTP_200_OK)
def login_user(user_login: UserLogin, service: UserService = Depends(get_user_service)) -> BaseResponse[User]:
    try:
        user = service.login(user_login)
        return BaseResponse(status="success", data=user, message="Login Success.") 
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@user.post("/register", response_model=BaseResponse[User], status_code=status.HTTP_201_CREATED)
def register_user(user: User, service: UserService = Depends(get_user_service)) -> BaseResponse[User]:
    """
    사용자의 로그인 요청을 처리한다.

    Args:
        user_login: 이메일과 비밀번호를 포함한 로그인 요청 데이터.
        service: 사용자 인증 로직을 수행하는 서비스 객체.

    Returns:
        로그인에 성공한 사용자 정보를 담은 공통 응답 객체.

    Raises:
        HTTPException: 로그인 정보가 올바르지 않은 경우 발생한다.
    """
    try:
        new_user = service.register_user(user)
        return BaseResponse(status="success", data=new_user, message="User registration success.")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@user.delete("/delete", response_model=BaseResponse[User], status_code=status.HTTP_200_OK)
def delete_user(user_delete_request: UserDeleteRequest, service: UserService = Depends(get_user_service)) -> BaseResponse[User]:
    """
    이메일을 기준으로 사용자를 삭제한다.

    Args:
        user_delete_request: 삭제할 사용자의 이메일을 포함한 요청 데이터.
        service: 사용자 삭제 로직을 수행하는 서비스 객체.

    Returns:
        삭제된 사용자 정보를 담은 공통 응답 객체.

    Raises:
        HTTPException: 삭제할 사용자를 찾을 수 없는 경우 발생한다.
    """
    try:
        deleted_user = service.delete_user(user_delete_request.email)
        return BaseResponse(status="success", data=deleted_user, message="User Deletion Success.")
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    

@user.put("/update-password", response_model=BaseResponse[User], status_code=status.HTTP_200_OK)
def update_user_password(user_update: UserUpdate, service: UserService = Depends(get_user_service)) -> BaseResponse[User]:
    """
    사용자의 비밀번호를 변경한다.

    Args:
        user_update: 사용자 식별 정보와 새 비밀번호를 포함한 요청 데이터.
        service: 비밀번호 변경 로직을 수행하는 서비스 객체.

    Returns:
        비밀번호가 변경된 사용자 정보를 담은 공통 응답 객체.

    Raises:
        HTTPException: 사용자를 찾을 수 없거나 변경에 실패한 경우 발생한다.
    """
    try:
        updated_user = service.update_user_pwd(user_update)
        return BaseResponse(status="success", data=updated_user, message="User password update success.")
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
