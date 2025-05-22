"""
Connecting to Redis with Python
--------------------------------

This guide demonstrates how to connect to a Redis free instance using Python.
"""

# 1. Install required package
# pip install redis

# 2. Import the Redis client
import redis

# 3. Connect to Redis
def connect_to_redis(host, port, password=None, ssl=False):
    """
    Establish a connection to Redis
    
    Args:
        host (str): Redis server hostname or IP
        port (int): Redis server port
        password (str, optional): Redis password for authentication
        ssl (bool): Whether to use SSL/TLS for the connection
        
    Returns:
        redis.Redis: Redis client connection
    """
    try:
        # Connection parameters
        connection_params = {
            'host': host,
            'port': port,
            'decode_responses': True  # Return strings instead of bytes
        }
        
        # Add password if provided
        if password:
            connection_params['password'] = password
            
        # Add SSL if enabled
        if ssl:
            connection_params['ssl'] = True
            
        # Create connection
        r = redis.Redis(**connection_params)
        
        # Test connection with a ping
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

# 4. Example usage
def main():
    # Replace with your Redis instance details
    REDIS_HOST = "orbit-knowledge-base"
    REDIS_PORT = 6379  # Default Redis port
    REDIS_API_KEY = "S2a5p7t44qwfzssaxvmq23qrh4gt9kf4l91dgw5p5c3r7ou3tx7"  # Your Redis API key
    USE_SSL = True  # Most cloud Redis services require SSL
    
    
    # Connect to Redis
    r = connect_to_redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        password=REDIS_API_KEY,  # Many Redis services use the API key as the password
        ssl=USE_SSL
    )
    
    if r:
        # Basic Redis operations
        # Set a key
        r.set('test_key', 'Hello from Python!')
        
        # Get a key
        value = r.get('test_key')
        print(f"Retrieved value: {value}")
        
        # Other common operations
        r.set('counter', 0)
        r.incr('counter')
        r.incr('counter')
        print(f"Counter value: {r.get('counter')}")
        
        # Store and retrieve a dictionary (using hash)
        r.hset('user:1000', mapping={
            'name': 'John Doe',
            'email': 'john@example.com',
            'age': '30'
        })
        
        user = r.hgetall('user:1000')
        print(f"User data: {user}")
        
        # Working with lists
        r.lpush('my_list', 'item1')
        r.lpush('my_list', 'item2')
        r.rpush('my_list', 'item3')
        
        list_items = r.lrange('my_list', 0, -1)
        print(f"List items: {list_items}")

if __name__ == "__main__":
    main()