import threading
import time

import schedule


class ReminderService:
    """
    Simple service for managing the schedule library's background thread.
    This service only handles starting and stopping the scheduler thread.
    """
    
    def __init__(self, db_path: str, reminder_queue=None):
        """
        Initialize the reminder service
        
        Args:
            db_path: Path parameter (kept for API compatibility but not used)
            reminder_queue: Queue parameter (kept for API compatibility but 
                not used)
        """
        self._running = False
        self._stop_event = None
    
    def start(self):
        """Start the scheduler in a background thread"""
        if not self._running:
            self._stop_event = threading.Event()
            
            # Start the background thread
            continuous_thread = threading.Thread(target=self._run_continuously)
            continuous_thread.daemon = True
            continuous_thread.start()
            
            self._running = True
    
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