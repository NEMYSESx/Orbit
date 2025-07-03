import json
import redis
import uuid
import os
from datetime import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

@dataclass
class Query:
    content: str
    timestamp: datetime

@dataclass
class Answer:
    content: str
    timestamp: datetime
    metadata: Optional[Dict[str, Any]] = None
    summary: Optional[str] = None

@dataclass
class ConversationSession:
    session_id: str
    messages: List[Dict[str, Any]] = field(default_factory=list)
    count: int = 0
    created_at: datetime = field(default_factory=datetime.now)

class ConversationManager:
    def __init__(self, 
                 redis_host: str = None, 
                 redis_port: int = None, 
                 redis_db: int = None, 
                 redis_password: Optional[str] = None):
        
        self.redis_host = redis_host or os.getenv('REDIS_HOST', 'localhost')
        self.redis_port = redis_port or int(os.getenv('REDIS_PORT', 6379))
        self.redis_db = redis_db or int(os.getenv('REDIS_DB', 0))
        self.redis_password = redis_password or os.getenv('REDIS_PASSWORD')
        
        self.session_ttl = 7200  
        self.max_messages_per_session = 16
        
        self.redis_config = {
            'host': self.redis_host,
            'port': self.redis_port,
            'db': self.redis_db,
            'password': self.redis_password,
            'decode_responses': True,
            'socket_timeout': 10,
            'socket_connect_timeout': 10,
            'retry_on_timeout': True,
            'health_check_interval': 30,
        }
        
        self.redis_client = redis.Redis(**self.redis_config)
        self.redis_client.ping()
        print("Redis connection established successfully")

    def serialize_query(self, query: Query) -> Dict[str, Any]:
        return {
            "content": query.content,
            "timestamp": query.timestamp.isoformat()
        }

    def serialize_answer(self, answer: Answer) -> Dict[str, Any]:
        return {
            "content": answer.content,
            "timestamp": answer.timestamp.isoformat(),
            "metadata": answer.metadata,
            "summary": answer.summary
        }

    def apply_sliding_window(self, messages: List[Dict[str, Any]], max_messages: int = 20) -> List[Dict[str, Any]]:
        return messages[-max_messages:]

    def create_session(self) -> Dict[str, Any]:
        session_id = str(uuid.uuid4())

        session = ConversationSession(session_id=session_id)

        session_data = {
            'session_id': session.session_id,
            'messages': [],
            'count': session.count,
            'created_at': session.created_at.isoformat(),
        }

        self.redis_client.setex(
            session_id,
            self.session_ttl,
            json.dumps(session_data)
        )
        print(f"Created session: {session_id}")
        return session_data

    def add_message(self, session_id: str, content_query: str ,content_answer: str, metadata: Optional[Dict[str, Any]] = None, summary: Optional[str] = None) -> Optional[Dict[str, Any]]:
        query = Query(
            content=content_query,
            timestamp=datetime.now(),
        )

        answer = Answer(
            content=content_answer,  
            timestamp=datetime.now(),
            metadata=metadata,
            summary=summary
        )

        session_data = self.redis_client.get(session_id)

        if not session_data:
            print(f"Session {session_id} not found. Creating new session.")
            session_dict = {
                'session_id': session_id,
                'messages': [],
                'count': 0,
                'created_at': datetime.now().isoformat()
            }
        else:
            session_dict = json.loads(session_data)

        session_dict['count'] += 1
        message_pair = {
            "count": session_dict['count'],
            "query": self.serialize_query(query),
            "answer": self.serialize_answer(answer)
        }

        session_dict['messages'].append(message_pair)
        session_dict['messages'] = self.apply_sliding_window(session_dict['messages'], self.max_messages_per_session)

        self.redis_client.setex(session_id, self.session_ttl, json.dumps(session_dict))

        print(f"Added message pair #{session_dict['count']} to session {session_id}")
        return session_dict

    def session_exists(self, session_id: str) -> bool:
        return self.redis_client.exists(session_id) > 0

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        session_data = self.redis_client.get(session_id)
        if session_data:
            return json.loads(session_data)
        print(f"Session {session_id} not found.")
        return None
