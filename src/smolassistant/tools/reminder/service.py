import threading
import time
import sqlite3
from datetime import datetime
import uuid

import schedule


class ReminderService:
    """
    Service for managing reminders with SQLite persistence.
    Handles starting/stopping the scheduler thread and database operations.
    """
    
    def __init__(self, db_path, reminder_queue=None):
        """
        Initialize the reminder service with database connection
        
        Args:
            db_path: Path to the SQLite database file
            reminder_queue: Queue for pushing reminder messages
        """
        self._running = False
        self._stop_event = None
        self._db_path = db_path
        self._reminder_queue = reminder_queue
        
        # Create a callback function for reminders
        self._callback_fn = None
        if reminder_queue:
            self._callback_fn = lambda msg: reminder_queue.put(msg)
        
        # Initialize the database
        self._init_db()
    
    def _init_db(self):
        """Initialize the database with required tables if they don't exist"""
        conn = sqlite3.connect(self._db_path)
        cursor = conn.cursor()
        
        # Create table for one-time reminders
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS one_time_reminders (
            id TEXT PRIMARY KEY,
            message TEXT NOT NULL,
            due_time TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        ''')
        
        # Create table for recurring reminders
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS recurring_reminders (
            id TEXT PRIMARY KEY,
            message TEXT NOT NULL,
            interval TEXT NOT NULL,
            time_spec TEXT,
            created_at TEXT NOT NULL
        )
        ''')
        
        conn.commit()
        conn.close()
    
    def start(self):
        """Start the scheduler in a background thread and load saved reminders"""
        if not self._running:
            self._stop_event = threading.Event()
            
            # Start the background thread
            continuous_thread = threading.Thread(target=self._run_continuously)
            continuous_thread.daemon = True
            continuous_thread.start()
            
            self._running = True
            
            # Load all saved reminders
            self._load_reminders()
    
    def _run_continuously(self):
        """Run the scheduler continuously until the stop event is set"""
        while not self._stop_event.is_set():
            schedule.run_pending()
            time.sleep(1)
    
    def stop(self):
        """Shutdown the scheduler"""
        if self._running:
            self._stop_event.set()
            self._running = False
            # Clear all scheduled jobs
            schedule.clear()
    
    def _load_reminders(self):
        """Load and recreate all reminders from the database"""
        if not self._callback_fn:
            return
            
        self._load_one_time_reminders()
        self._load_recurring_reminders()
    
    def _load_one_time_reminders(self):
        """Load and recreate one-time reminders from the database"""
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM one_time_reminders')
        reminders = cursor.fetchall()
        
        for reminder in reminders:
            # Parse due_time
            due_time = datetime.fromisoformat(reminder['due_time'])
            now = datetime.now()
            
            # If due time is in the future, schedule it
            if due_time > now:
                # Calculate seconds until due
                seconds_until_due = (due_time - now).total_seconds()
                
                # Recreate the reminder
                self.create_one_time_reminder(
                    reminder['message'],
                    reminder['id'],
                    seconds_until_due
                )
            else:
                # Due time has already passed, trigger immediately
                formatted_message = f"🔔 REMINDER: {reminder['message']}"
                if self._callback_fn:
                    self._callback_fn(formatted_message)
                
                # And remove from database
                self.delete_one_time_reminder(reminder['id'])
        
        conn.close()
    
    def _load_recurring_reminders(self):
        """Load and recreate recurring reminders from the database"""
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM recurring_reminders')
        reminders = cursor.fetchall()
        
        for reminder in reminders:
            # Recreate the recurring reminder
            self.create_recurring_reminder(
                reminder['message'],
                reminder['id'],
                reminder['interval'],
                reminder['time_spec'] if reminder['time_spec'] else ""
            )
        
        conn.close()
    
    def create_one_time_reminder(self, message, reminder_id=None, seconds_until_due=None, due_time=None):
        """
        Create a one-time reminder in both schedule and database
        
        Args:
            message: The reminder message
            reminder_id: Optional ID for the reminder (generated if not provided)
            seconds_until_due: Seconds until the reminder is due
            due_time: ISO format datetime when the reminder should trigger
                      (required if seconds_until_due is not provided)
        
        Returns:
            tuple: (reminder_id, job)
        """
        if not self._callback_fn:
            return None, None
            
        # Generate a unique ID if not provided
        if not reminder_id:
            reminder_id = f"reminder_{uuid.uuid4()}"
        
        # If seconds_until_due not provided, calculate from due_time
        if seconds_until_due is None:
            if due_time is None:
                return None, None
                
            try:
                parsed_time = datetime.fromisoformat(due_time)
                now = datetime.now()
                seconds_until_due = (parsed_time - now).total_seconds()
            except (ValueError, TypeError):
                return None, None
        
        # Define the job function
        def reminder_job(message=None, reminder_id=None):
            formatted_message = f"🔔 REMINDER: {message}"
            self._callback_fn(formatted_message)
            
            # Remove from database
            self.delete_one_time_reminder(reminder_id)
            
            # Return CancelJob to remove the job after it runs
            return schedule.CancelJob
        
        # Schedule the job
        job = schedule.every(seconds_until_due).seconds.do(
            reminder_job,
            message=message,
            reminder_id=reminder_id
        )
        job.tag('reminder', reminder_id)
        
        # Save to database if due_time is provided
        if due_time and seconds_until_due > 0:
            conn = sqlite3.connect(self._db_path)
            cursor = conn.cursor()
            
            try:
                cursor.execute(
                    'INSERT OR REPLACE INTO one_time_reminders VALUES (?, ?, ?, ?)',
                    (
                        reminder_id, 
                        message, 
                        due_time, 
                        datetime.now().isoformat()
                    )
                )
                conn.commit()
            except sqlite3.Error:
                # Log error or handle gracefully
                pass
            finally:
                conn.close()
        
        return reminder_id, job
    
    def create_recurring_reminder(self, message, reminder_id=None, interval=None, time_spec=""):
        """
        Create a recurring reminder in both schedule and database
        
        Args:
            message: The reminder message
            reminder_id: Optional ID for the reminder (generated if not provided)
            interval: The recurrence pattern
            time_spec: Optional time specification
        
        Returns:
            tuple: (reminder_id, job)
        """
        if not self._callback_fn or not interval:
            return None, None
            
        # Generate a unique ID if not provided
        if not reminder_id:
            reminder_id = f"recurring_{uuid.uuid4()}"
        
        # Define the job function
        def reminder_job(message=None, reminder_id=None, interval=None, time_spec=None):
            if time_spec:
                formatted_message = f"🔄 RECURRING REMINDER ({interval} at {time_spec}): {message}"
            else:
                formatted_message = f"🔄 RECURRING REMINDER ({interval}): {message}"
            self._callback_fn(formatted_message)
        
        # Create mapped dictionaries for the schedule methods
        interval_methods = {
            # Basic intervals
            "second": schedule.every().second,
            "minute": schedule.every().minute,
            "hour": schedule.every().hour,
            "day": schedule.every().day,
            
            # Days of week
            "monday": schedule.every().monday,
            "tuesday": schedule.every().tuesday,
            "wednesday": schedule.every().wednesday,
            "thursday": schedule.every().thursday,
            "friday": schedule.every().friday,
            "saturday": schedule.every().saturday,
            "sunday": schedule.every().sunday,
        }
        
        job = None
        display_interval = interval.lower()
        
        # Check for numbered intervals like "2 hours"
        interval_parts = interval.lower().split()
        if len(interval_parts) == 2 and interval_parts[0].isdigit():
            count = int(interval_parts[0])
            unit = interval_parts[1]
            
            # Handle plural forms by removing trailing 's'
            if unit.endswith('s'):
                unit = unit[:-1]
            
            # Map the unit to the correct schedule method
            if unit == "second":
                job = schedule.every(count).seconds.do(
                    reminder_job,
                    message=message,
                    reminder_id=reminder_id,
                    interval=display_interval,
                    time_spec=time_spec
                )
            elif unit == "minute":
                job = schedule.every(count).minutes.do(
                    reminder_job,
                    message=message,
                    reminder_id=reminder_id,
                    interval=display_interval,
                    time_spec=time_spec
                )
            elif unit == "hour":
                job = schedule.every(count).hours.do(
                    reminder_job,
                    message=message,
                    reminder_id=reminder_id,
                    interval=display_interval,
                    time_spec=time_spec
                )
            elif unit == "day":
                job = schedule.every(count).days.do(
                    reminder_job,
                    message=message,
                    reminder_id=reminder_id,
                    interval=display_interval,
                    time_spec=time_spec
                )
        else:
            # Handle standard intervals
            method = interval_methods.get(interval.lower())
            
            if method:
                if time_spec:
                    # With time specification
                    job = method.at(time_spec).do(
                        reminder_job,
                        message=message,
                        reminder_id=reminder_id,
                        interval=display_interval,
                        time_spec=time_spec
                    )
                else:
                    # Without time specification
                    job = method.do(
                        reminder_job,
                        message=message,
                        reminder_id=reminder_id,
                        interval=display_interval,
                        time_spec=time_spec
                    )
        
        if job:
            # Tag the job for identification and management
            job.tag('recurring', reminder_id)
            
            # Save to database
            conn = sqlite3.connect(self._db_path)
            cursor = conn.cursor()
            
            try:
                cursor.execute(
                    'INSERT OR REPLACE INTO recurring_reminders VALUES (?, ?, ?, ?, ?)',
                    (
                        reminder_id, 
                        message, 
                        interval, 
                        time_spec, 
                        datetime.now().isoformat()
                    )
                )
                conn.commit()
            except sqlite3.Error:
                # Log error or handle gracefully
                pass
            finally:
                conn.close()
        
        return reminder_id, job
    
    def delete_one_time_reminder(self, reminder_id):
        """
        Delete a one-time reminder from both schedule and database
        
        Args:
            reminder_id: ID of the reminder to delete
            
        Returns:
            bool: True if successful
        """
        # Clear the job from schedule
        schedule.clear(reminder_id)
        
        # Remove from database
        conn = sqlite3.connect(self._db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                'DELETE FROM one_time_reminders WHERE id = ?',
                (reminder_id,)
            )
            conn.commit()
            success = True
        except sqlite3.Error:
            success = False
        finally:
            conn.close()
        
        return success
    
    def delete_recurring_reminder(self, reminder_id):
        """
        Delete a recurring reminder from both schedule and database
        
        Args:
            reminder_id: ID of the reminder to delete
            
        Returns:
            bool: True if successful
        """
        # Clear the job from schedule
        schedule.clear(reminder_id)
        
        # Remove from database
        conn = sqlite3.connect(self._db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                'DELETE FROM recurring_reminders WHERE id = ?',
                (reminder_id,)
            )
            conn.commit()
            success = True
        except sqlite3.Error:
            success = False
        finally:
            conn.close()
        
        return success
    
    def get_one_time_reminders(self):
        """
        Get all one-time reminders from the database
        
        Returns:
            list: List of dictionaries containing reminder data
        """
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM one_time_reminders')
        reminders = [dict(reminder) for reminder in cursor.fetchall()]
        
        conn.close()
        return reminders
    
    def get_recurring_reminders(self):
        """
        Get all recurring reminders from the database
        
        Returns:
            list: List of dictionaries containing reminder data
        """
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM recurring_reminders')
        reminders = [dict(reminder) for reminder in cursor.fetchall()]
        
        conn.close()
        return reminders
