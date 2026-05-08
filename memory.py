import re
import sqlite3
from datetime import datetime

class SQLiteMemory:
    def __init__(self, db_path='memory.db'):
        self.db_path = db_path
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.create_table()

    def create_table(self):
        with self.conn:
            self.conn.execute('''
                CREATE TABLE IF NOT EXISTS memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT,
                    query TEXT,
                    response TEXT,
                    timestamp TEXT
                )
            ''')
            self.conn.execute('''
                CREATE TABLE IF NOT EXISTS user_info (
                    user_id TEXT PRIMARY KEY,
                    name TEXT
                )
            ''')

    def set_user_name(self, user_id, name):
        with self.conn:
            self.conn.execute('''
                INSERT OR REPLACE INTO user_info (user_id, name)
                VALUES (?, ?)
            ''', (user_id, name))

    def get_user_name(self, user_id):
        cursor = self.conn.cursor()
        cursor.execute('SELECT name FROM user_info WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        return result[0] if result else None

    def save_memory(self, user_id, query, response):
        timestamp = datetime.now().isoformat()
        with self.conn:
            self.conn.execute('''
                INSERT INTO memory (user_id, query, response, timestamp)
                VALUES (?, ?, ?, ?)
            ''', (user_id, query, response, timestamp))

    async def search_memory(self, user_id, user_query, n_results=3):
        """Enhanced memory search that looks at both queries and responses"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT query, response FROM memory
            WHERE user_id = ?
            AND (query LIKE ? OR response LIKE ?)
            ORDER BY timestamp DESC
            LIMIT ?
        ''', (user_id, f'%{user_query}%', f'%{user_query}%', n_results))
        return [f"Q: {row[0]}\nA: {row[1]}" for row in cursor.fetchall()]

    def get_related_memories(self, user_id, text, n_results=3):
        """Get memories related to the current context"""
        keywords = self._extract_keywords(text)
        cursor = self.conn.cursor()
        query_params = [user_id]
        like_clauses = []
        
        for keyword in keywords:
            query_params.extend([f'%{keyword}%', f'%{keyword}%'])
            like_clauses.append("(query LIKE ? OR response LIKE ?)")
        
        if not like_clauses:
            return []
            
        query = f'''
            SELECT query, response FROM memory
            WHERE user_id = ? AND ({' OR '.join(like_clauses)})
            ORDER BY timestamp DESC
            LIMIT ?
        '''
        query_params.append(n_results)
        
        cursor.execute(query, query_params)
        return [f"Q: {row[0]}\nA: {row[1]}" for row in cursor.fetchall()]

    def _extract_keywords(self, text):
        """Simple keyword extraction"""
        stop_words = {'the', 'and', 'is', 'are', 'i', 'you', 'me'}
        words = re.findall(r'\w+', text.lower())
        return [word for word in words if word not in stop_words][:5]

    def get_chat_history(self, user_id, limit=20):
        """Get all chat history for a user"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT query, response, timestamp FROM memory
            WHERE user_id = ?
            ORDER BY timestamp DESC 
            LIMIT ?
        ''', (user_id, limit))
        return cursor.fetchall()


# import re
# import sqlite3
# from datetime import datetime

# class SQLiteMemory:
#     def __init__(self, db_path='memory.db'):
#         self.db_path = db_path
#         self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
#         self.create_table()

#     def create_table(self):
#         with self.conn:
#             self.conn.execute('''
#                 CREATE TABLE IF NOT EXISTS memory (
#                     id INTEGER PRIMARY KEY AUTOINCREMENT,
#                     user_id TEXT,
#                     query TEXT,
#                     response TEXT,
#                     timestamp TEXT
#                 )
#             ''')
#             self.conn.execute('''
#                 CREATE TABLE IF NOT EXISTS user_info (
#                     user_id TEXT PRIMARY KEY,
#                     name TEXT
#                 )
#             ''')

#     def set_user_name(self, user_id, name):
#         with self.conn:
#             self.conn.execute('''
#                 INSERT OR REPLACE INTO user_info (user_id, name)
#                 VALUES (?, ?)
#             ''', (user_id, name))

#     def get_user_name(self, user_id):
#         cursor = self.conn.cursor()
#         cursor.execute('SELECT name FROM user_info WHERE user_id = ?', (user_id,))
#         result = cursor.fetchone()
#         return result[0] if result else None

#     def save_memory(self, user_id, query, response):
#         timestamp = datetime.now().isoformat()
#         with self.conn:
#             self.conn.execute('''
#                 INSERT INTO memory (user_id, query, response, timestamp)
#                 VALUES (?, ?, ?, ?)
#             ''', (user_id, query, response, timestamp))

#     def search_memory(self, user_id, user_query, n_results=3):
#         """Enhanced memory search that looks at both queries and responses"""
#         cursor = self.conn.cursor()
#         cursor.execute('''
#             SELECT query, response FROM memory
#             WHERE user_id = ?
#             AND (query LIKE ? OR response LIKE ?)
#             ORDER BY timestamp DESC
#             LIMIT ?
#         ''', (user_id, f'%{user_query}%', f'%{user_query}%', n_results))
#         return [f"Q: {row[0]}\nA: {row[1]}" for row in cursor.fetchall()]

#     def get_related_memories(self, user_id, text, n_results=3):
#         """Get memories related to the current context"""
#         keywords = self._extract_keywords(text)
#         cursor = self.conn.cursor()
#         query_params = [user_id]
#         like_clauses = []
        
#         for keyword in keywords:
#             query_params.extend([f'%{keyword}%', f'%{keyword}%'])
#             like_clauses.append("(query LIKE ? OR response LIKE ?)")
        
#         if not like_clauses:
#             return []
            
#         query = f'''
#             SELECT query, response FROM memory
#             WHERE user_id = ? AND ({' OR '.join(like_clauses)})
#             ORDER BY timestamp DESC
#             LIMIT ?
#         '''
#         query_params.append(n_results)
        
#         cursor.execute(query, query_params)
#         return [f"Q: {row[0]}\nA: {row[1]}" for row in cursor.fetchall()]

#     def _extract_keywords(self, text):
#         """Simple keyword extraction"""
#         stop_words = {'the', 'and', 'is', 'are', 'i', 'you', 'me'}
#         words = re.findall(r'\w+', text.lower())
#         return [word for word in words if word not in stop_words][:5]

#     def get_chat_history(self, user_id, limit=20):
#         """Get all chat history for a user"""
#         cursor = self.conn.cursor()
#         cursor.execute('''
#             SELECT query, response, timestamp FROM memory
#             WHERE user_id = ?
#             ORDER BY timestamp DESC 
#             LIMIT ?
#         ''', (user_id, limit))
#         return cursor.fetchall()
    

# import sqlite3
# from datetime import datetime

# class SQLiteMemory:
#     def __init__(self, db_path='memory.db'):
#         self.db_path = db_path
#         self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
#         self.create_table()

#     def create_table(self):
#         with self.conn:
#             self.conn.execute('''
#                 CREATE TABLE IF NOT EXISTS memory (
#                     id INTEGER PRIMARY KEY AUTOINCREMENT,
#                     user_id TEXT,
#                     query TEXT,
#                     response TEXT,
#                     timestamp TEXT
#                 )
#             ''')
#             self.conn.execute('''
#                 CREATE TABLE IF NOT EXISTS user_info (
#                     user_id TEXT PRIMARY KEY,
#                     name TEXT
#                 )
#             ''')
   
#     def set_user_name(self, user_id, name):
#         with self.conn:
#             self.conn.execute('''
#                 INSERT OR REPLACE INTO user_info (user_id, name)
#                 VALUES (?, ?)
#             ''', (user_id, name))
    
#     def get_user_name(self, user_id):
#         cursor = self.conn.cursor()
#         cursor.execute('SELECT name FROM user_info WHERE user_id = ?', (user_id,))
#         result = cursor.fetchone()
#         return result[0] if result else None
    
#     def save_memory(self, user_id, query, response):
#         timestamp = datetime.now().isoformat()
#         with self.conn:
#             self.conn.execute('''
#                 INSERT INTO memory (user_id, query, response, timestamp)
#                 VALUES (?, ?, ?, ?)
#             ''', (user_id, query, response, timestamp))

#     async def search_memory(self, user_id, user_query, n_results=3):
#         cursor = self.conn.cursor()
#         cursor.execute('''
#             SELECT response FROM memory
#             WHERE user_id = ?
#             AND query LIKE ?
#             ORDER BY timestamp DESC
#             LIMIT ?
#         ''', (user_id, f'%{user_query}%', n_results))
#         results = cursor.fetchall()
#         return [row[0] for row in results]

#     # Add this new method to fix the error
#     def get_all_memories(self):
#         cursor = self.conn.cursor()
#         cursor.execute('''
#             SELECT query, response, timestamp FROM memory
#             ORDER BY timestamp DESC
#         ''')
#         return cursor.fetchall()
#     def get_chat_history(self, user_id, limit=20):
#          """Get all chat history for a user"""
#          cursor = self.conn.cursor()
#          cursor.execute('''
#              SELECT query, response, timestamp FROM memory
#              WHERE user_id = ?
#              ORDER BY timestamp DESC 
#              LIMIT ?
#          ''', (user_id, limit))
#          return cursor.fetchall()
    