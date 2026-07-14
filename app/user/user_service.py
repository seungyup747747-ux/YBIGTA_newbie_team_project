from app.user.user_repository import UserRepository
from app.user.user_schema import User, UserLogin, UserUpdate


class UserService:
    def __init__(self, userRepoitory: UserRepository) -> None:
        self.repo = userRepoitory

    def login(self, user_login: UserLogin) -> User:
        """이메일과 비밀번호를 검증하여 사용자를 로그인 처리한다.

        전달받은 이메일을 이용하여 Repository에서 사용자를 조회한다.
        사용자가 존재하면 입력된 비밀번호와 저장된 비밀번호를 비교하고,
        두 값이 일치하는 경우 해당 사용자 객체를 반환한다.

        Args:
            user_login: 로그인에 사용할 이메일과 비밀번호가 담긴 객체.

        Returns:
            인증에 성공한 사용자 객체.

        Raises:
            ValueError: 입력된 이메일에 해당하는 사용자가 존재하지 않는 경우.
            ValueError: 입력된 비밀번호가 저장된 비밀번호와 일치하지 않는 경우.
        """
        user = self.repo.get_user_by_email(user_login.email)

        if user is None:
            raise ValueError("User not Found.")

        if user.password != user_login.password:
            raise ValueError("Invalid ID/PW")

        return user

    def register_user(self, new_user: User) -> User:
        """이메일 중복 여부를 확인한 후 새로운 사용자를 등록한다.

        전달받은 사용자의 이메일로 기존 사용자를 조회한다.
        동일한 이메일을 사용하는 사용자가 없으면 Repository를 통해
        새로운 사용자 정보를 저장한다.

        Args:
            new_user: 등록할 사용자의 이메일, 비밀번호, 사용자 이름이
                담긴 객체.

        Returns:
            Repository에 저장된 사용자 객체.

        Raises:
            ValueError: 동일한 이메일을 사용하는 사용자가 이미 존재하는 경우.
        """
        existing_user = self.repo.get_user_by_email(new_user.email)

        if existing_user is not None:
            raise ValueError("User already Exists.")

        return self.repo.save_user(new_user)

    def delete_user(self, email: str) -> User:
        """이메일에 해당하는 사용자를 조회하여 삭제한다.

        전달받은 이메일을 이용하여 Repository에서 사용자를 조회한다.
        사용자가 존재하면 해당 사용자 객체를 Repository에 전달하여
        저장소에서 삭제한다.

        Args:
            email: 삭제할 사용자의 이메일 주소.

        Returns:
            Repository에서 삭제된 사용자 객체.

        Raises:
            ValueError: 입력된 이메일에 해당하는 사용자가 존재하지 않는 경우.
        """
        user = self.repo.get_user_by_email(email)

        if user is None:
            raise ValueError("User not Found.")

        return self.repo.delete_user(user)

    def update_user_pwd(self, user_update: UserUpdate) -> User:
        """기존 사용자의 비밀번호를 새로운 비밀번호로 변경한다.

        전달받은 이메일로 기존 사용자를 조회한다. 사용자가 존재하면
        사용자 객체의 비밀번호를 새로운 비밀번호로 변경하고,
        수정된 사용자 객체를 Repository에 다시 저장한다.

        Args:
            user_update: 사용자의 이메일과 변경할 새 비밀번호가 담긴 객체.

        Returns:
            비밀번호가 변경되어 Repository에 저장된 사용자 객체.

        Raises:
            ValueError: 입력된 이메일에 해당하는 사용자가 존재하지 않는 경우.
        """
        user = self.repo.get_user_by_email(user_update.email)

        if user is None:
            raise ValueError("User not Found.")

        user.password = user_update.new_password

        return self.repo.save_user(user)