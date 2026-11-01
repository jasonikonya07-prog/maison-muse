from fastapi import APIRouter

from app.database import get_connection
from app.schemas import NewsletterSignup


router = APIRouter()


@router.post("/newsletter")
def subscribe_to_newsletter(signup: NewsletterSignup) -> dict[str, str]:
    with get_connection() as connection:
        connection.execute(
            "INSERT OR IGNORE INTO newsletter_subscribers (email) VALUES (?)",
            (signup.email,),
        )
        connection.commit()

    return {
        "message": (
            "You’re on the list. Newsletter delivery isn’t configured yet, "
            "so you won’t receive campaign emails just yet."
        )
    }
