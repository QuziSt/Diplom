from redis import Redis


redis_storage = Redis(host='redis', port=6379, db=6)

