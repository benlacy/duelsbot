
import aiohttp
import asyncio
import os

RLSTATS_API_KEY = os.getenv("RLSTATS_API_KEY")

# Maps for platform and playlist names to their IDs
PLATFORM_MAP = {
    "steam": 1,
    "ps4": 2,
    "xbox": 3,
    "switch": 4,
    "epic": 5
}

PLAYLIST_MAP = {
    "unranked": '0',
    "duel": '10',
    "doubles": '11',
    "solo standard": '12',
    "standard": '13',
    "hoops": '27',
    "rumble": '28',
    "dropshot": '29',
    "snow day": '30',
    "tournament": '34'
}

def get_platform_id(platform_name: str) -> int | None:
    return PLATFORM_MAP.get(platform_name.strip().lower())

def get_playlist_id(playlist_name: str) -> int | None:
    return PLAYLIST_MAP.get(playlist_name.strip().lower())


async def get_player_stats(platform_id, player_id):
    url = f"https://api.rlstats.net/v1/profile/stats"
    params = {
        "apikey": RLSTATS_API_KEY,
        "platformid": get_platform_id(platform_id),
        "playerid": player_id
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as response:
            if response.status == 200:
                return await response.json()
            else:
                print(f"Failed: {response.status}")
                print(await response.text())
                return None

async def get_player_mmr(platform_id, player_id, playlist_id=PLAYLIST_MAP['duel']):
    data = await get_player_stats(platform_id, player_id)
    if data:
        season = str(data['SeasonInfo']['SeasonID'])
        return data['RankedSeasons'][season][playlist_id]['SkillRating']
    return None

# asyncio.run(get_player_mmr("steam", "76561198251007520"))