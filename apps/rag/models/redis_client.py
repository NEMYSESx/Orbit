import redis

def connect_to_redis(host, port, password=None, ssl=False):
    try:
        connection_params = {
            'host': host,
            'port': port,
            'decode_responses': True  
        }
        
        if password:
            connection_params['password'] = password
            
        if ssl:
            connection_params['ssl'] = True
            
        r = redis.Redis(**connection_params)
        
        if r.ping():
            print("Successfully connected to Redis!")
            return r
        else:
            print("Connected but ping failed.")
            return None
            
    except redis.exceptions.ConnectionError as e:
        print(f"Connection Error: {e}")
        return None
    except Exception as e:
        print(f"Error: {e}")
        return None

def main():
    REDIS_HOST = "orbit-knowledge-base"
    REDIS_PORT = 6379  
    REDIS_API_KEY = "S2a5p7t44qwfzssaxvmq23qrh4gt9kf4l91dgw5p5c3r7ou3tx7"  
    USE_SSL = True  
    
    
    r = connect_to_redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        password=REDIS_API_KEY, 
        ssl=USE_SSL
    )
    
    if r:
        r.set('test_key', 'Hello from Python!')
        
        value = r.get('test_key')
        print(f"Retrieved value: {value}")
        
        r.set('counter', 0)
        r.incr('counter')
        r.incr('counter')
        print(f"Counter value: {r.get('counter')}")
        
        r.hset('user:1000', mapping={
            'name': 'John Doe',
            'email': 'john@example.com',
            'age': '30'
        })
        
        user = r.hgetall('user:1000')
        print(f"User data: {user}")
        
        r.lpush('my_list', 'item1')
        r.lpush('my_list', 'item2')
        r.rpush('my_list', 'item3')
        
        list_items = r.lrange('my_list', 0, -1)
        print(f"List items: {list_items}")

if __name__ == "__main__":
    main()