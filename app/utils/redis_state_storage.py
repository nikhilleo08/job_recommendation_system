# import json
# import uuid
# from app.wrappers.cache_wrappers import CacheUtils


# class RedisStateStorage:
#     async def save_state(self, state: dict, ttl: int = 300) -> str:
#         key = f"oauth_state:{uuid.uuid4().hex}"
#         await CacheUtils.create_cache(json.dumps(state), key, ex=ttl)
#         return key

#     async def get_state(self, key: str) -> dict | None:
#         data, _ = await CacheUtils.retrieve_cache(key)
#         return json.loads(data) if data else None

#     async def delete_state(self, key: str):
#         await CacheUtils.invalidate_cache(key)

# app/wrappers/redis_state_storage.py
import json
import uuid
from app.wrappers.cache_wrappers import CacheUtils

class RedisStateStorage:
    """Store and retrieve OAuth 'state' using Redis via CacheUtils."""

    async def set(self, data: dict, ttl: int = 300) -> str:
        key = f"oauth_state:{uuid.uuid4().hex}"
        await CacheUtils.create_cache(json.dumps(data), key, ex=ttl)
        return key

    async def get(self, key: str) -> dict | None:
        data, _ = await CacheUtils.retrieve_cache(key)
        return json.loads(data) if data else None

    async def delete(self, key: str):
        await CacheUtils.invalidate_cache(key)


