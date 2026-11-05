from dotenv import load_dotenv
from prisma import Prisma

load_dotenv()

database = Prisma()


async def connect_database() -> None:
    if not database.is_connected():
        await database.connect()


async def disconnect_database() -> None:
    if database.is_connected():
        await database.disconnect()


def get_database() -> Prisma:
    return database
