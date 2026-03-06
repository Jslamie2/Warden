import sqlite3
import os
import socket
import getpass
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), 'warden.db')

def get_connection():
    """Get a database connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize the database with required tables."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            display_name TEXT,
            computer_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Miners table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS miners (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mac_address TEXT NOT NULL UNIQUE,
            ip_address TEXT,
            first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Reports table - tracks who reported which miner
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            miner_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            reported_ip TEXT,
            reported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (miner_id) REFERENCES miners(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')
    
    # Visits table - tracks who visited which miner
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS visits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            miner_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            visited_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (miner_id) REFERENCES miners(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')
    
    conn.commit()
    conn.close()

def get_or_create_user(username=None, display_name=None, computer_name=None):
    """Get existing user or create new one."""
    if username is None:
        username = getpass.getuser()
    if computer_name is None:
        computer_name = socket.gethostname()
    
    conn = get_connection()
    cursor = conn.cursor()
    
    # Try to get existing user
    cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
    user = cursor.fetchone()
    
    if user:
        # Update display name if provided
        if display_name:
            cursor.execute('UPDATE users SET display_name = ? WHERE username = ?', 
                         (display_name, username))
            conn.commit()
            cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
            user = cursor.fetchone()
    else:
        # Create new user
        cursor.execute(
            'INSERT INTO users (username, display_name, computer_name) VALUES (?, ?, ?)',
            (username, display_name or username, computer_name)
        )
        conn.commit()
        cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
        user = cursor.fetchone()
    
    conn.close()
    return dict(user) if user else None

def get_user_by_id(user_id):
    """Get user by ID."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
    user = cursor.fetchone()
    conn.close()
    return dict(user) if user else None

def report_miner(mac_address, ip_address, user_id):
    """Report a new miner or update existing one."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Check if miner exists
    cursor.execute('SELECT * FROM miners WHERE mac_address = ?', (mac_address,))
    miner = cursor.fetchone()
    
    miner_id = None
    is_new = False
    
    if miner:
        # Update existing miner
        cursor.execute(
            'UPDATE miners SET ip_address = ?, last_seen = CURRENT_TIMESTAMP WHERE mac_address = ?',
            (ip_address, mac_address)
        )
        miner_id = miner['id']
    else:
        # Create new miner
        cursor.execute(
            'INSERT INTO miners (mac_address, ip_address) VALUES (?, ?)',
            (mac_address, ip_address)
        )
        miner_id = cursor.lastrowid
        is_new = True
    
    # Record the report
    cursor.execute(
        'INSERT INTO reports (miner_id, user_id, reported_ip) VALUES (?, ?, ?)',
        (miner_id, user_id, ip_address)
    )
    
    conn.commit()
    conn.close()
    
    return miner_id, is_new

def mark_visited(miner_id, user_id):
    """Mark a miner as visited by a user."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Check if already visited by this user
    cursor.execute(
        'SELECT * FROM visits WHERE miner_id = ? AND user_id = ?',
        (miner_id, user_id)
    )
    if not cursor.fetchone():
        cursor.execute(
            'INSERT INTO visits (miner_id, user_id) VALUES (?, ?)',
            (miner_id, user_id)
        )
        conn.commit()
    
    conn.close()

def get_miner_visits(miner_id):
    """Get all visits for a miner."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT v.*, u.username, u.display_name, u.computer_name
        FROM visits v
        JOIN users u ON v.user_id = u.id
        WHERE v.miner_id = ?
        ORDER BY v.visited_at DESC
    ''', (miner_id,))
    visits = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return visits

def get_miner_reports(miner_id):
    """Get all reports for a miner."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT r.*, u.username, u.display_name, u.computer_name
        FROM reports r
        JOIN users u ON r.user_id = u.id
        WHERE r.miner_id = ?
        ORDER BY r.reported_at DESC
    ''', (miner_id,))
    reports = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return reports

def get_all_miners():
    """Get all miners with their visit status."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT m.*, 
               (SELECT COUNT(*) FROM visits WHERE miner_id = m.id) as visit_count,
               (SELECT COUNT(*) FROM reports WHERE miner_id = m.id) as report_count
        FROM miners m
        ORDER BY m.last_seen DESC
    ''')
    miners = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return miners

def get_unvisited_miners():
    """Get all miners that haven't been visited by any user."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT m.*, 
               (SELECT COUNT(*) FROM visits WHERE miner_id = m.id) as visit_count
        FROM miners m
        WHERE (SELECT COUNT(*) FROM visits WHERE miner_id = m.id) = 0
        ORDER BY m.last_seen DESC
    ''')
    miners = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return miners

def get_user_visited_miners(user_id):
    """Get miners visited by a specific user."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT m.* FROM miners m
        JOIN visits v ON m.id = v.miner_id
        WHERE v.user_id = ?
        ORDER BY v.visited_at DESC
    ''', (user_id,))
    miners = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return miners

def get_all_users():
    """Get all users."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users ORDER BY username')
    users = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return users

def get_user_pending_miner(user_id):
    """Get the next pending miner for a user that hasn't been visited yet."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Get miners reported by this user that haven't been visited by this user
    cursor.execute('''
        SELECT m.*, r.id as report_id
        FROM miners m
        JOIN reports r ON m.id = r.miner_id
        WHERE r.user_id = ?
        AND m.id NOT IN (SELECT miner_id FROM visits WHERE user_id = ?)
        ORDER BY r.reported_at ASC
        LIMIT 1
    ''', (user_id, user_id))
    
    miner = cursor.fetchone()
    conn.close()
    return dict(miner) if miner else None

def get_user_pending_count(user_id):
    """Get count of pending miners for a user."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT COUNT(*) as count
        FROM miners m
        JOIN reports r ON m.id = r.miner_id
        WHERE r.user_id = ?
        AND m.id NOT IN (SELECT miner_id FROM visits WHERE user_id = ?)
    ''', (user_id, user_id))
    
    result = cursor.fetchone()
    conn.close()
    return result['count'] if result else 0

def delete_miner(miner_id):
    """Delete a miner and all related records."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Delete visits first
    cursor.execute('DELETE FROM visits WHERE miner_id = ?', (miner_id,))
    # Delete reports
    cursor.execute('DELETE FROM reports WHERE miner_id = ?', (miner_id,))
    # Delete miner
    cursor.execute('DELETE FROM miners WHERE id = ?', (miner_id,))
    
    conn.commit()
    conn.close()

def get_user_visited_miners_with_info(user_id):
    """Get all miners visited by a user with visit info."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT m.*, v.visited_at, v.user_id as visit_user_id
        FROM miners m
        JOIN visits v ON m.id = v.miner_id
        WHERE v.user_id = ?
        ORDER BY v.visited_at DESC
    ''', (user_id,))
    miners = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return miners

