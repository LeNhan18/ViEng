import asyncio
from app.db.database import _get_engine_and_sessionmaker
from sqlalchemy import text

async def main():
    e, sf = _get_engine_and_sessionmaker()
    async with sf() as session:
        res = await session.execute(text('SELECT 1'))
        print(res.scalar())

asyncio.run(main())
