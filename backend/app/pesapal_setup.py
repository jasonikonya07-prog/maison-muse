from pathlib import Path

from dotenv import load_dotenv

from app.pesapal import PesapalError, register_ipn_url


def main() -> None:
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    try:
        ipn_id = register_ipn_url()
    except PesapalError as error:
        raise SystemExit(f"Could not register the Pesapal IPN URL: {error}") from error
    print(f"Set PESAPAL_IPN_ID={ipn_id} in backend/.env")


if __name__ == "__main__":
    main()
