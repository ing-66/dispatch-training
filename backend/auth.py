from dataclasses import dataclass


@dataclass(frozen=True)
class TrainingIdentity:
    external_source: str | None
    external_user_id: str | None
    display_name: str


class LocalAuthAdapter:
    def resolve(self, local_user_id: str, display_name: str) -> TrainingIdentity:
        return TrainingIdentity(None, local_user_id, display_name)


class ExternalAuthAdapter:
    """Maps a verified upstream identity to a training identity; token verification belongs at the deployment edge."""

    def resolve(self, source: str, external_user_id: str, display_name: str) -> TrainingIdentity:
        return TrainingIdentity(source, external_user_id, display_name)
