"""
The actions taken when each menubar option is clicked
"""

import logging
import threading
import time
import webbrowser
from tkinter import filedialog, messagebox

import grpc

from core.gui.appconfig import XMLS_PATH
from core.gui.dialogs.about import AboutDialog
from core.gui.dialogs.canvassizeandscale import SizeAndScaleDialog
from core.gui.dialogs.canvaswallpaper import CanvasWallpaperDialog
from core.gui.dialogs.hooks import HooksDialog
from core.gui.dialogs.observers import ObserverDialog
from core.gui.dialogs.preferences import PreferencesDialog
from core.gui.dialogs.servers import ServersDialog
from core.gui.dialogs.sessionoptions import SessionOptionsDialog
from core.gui.dialogs.sessions import SessionsDialog


class MenuAction:
    """
    Actions performed when choosing menu items
    """

    def __init__(self, app, master):
        self.master = master
        self.app = app

    def cleanup_old_session(self, quitapp=False):
        logging.info("cleaning up old session")
        start = time.perf_counter()
        self.app.core.stop_session()
        self.app.core.delete_session()
        process_time = time.perf_counter() - start
        self.app.statusbar.stop_session_callback(process_time)
        if quitapp:
            self.app.quit()

    def prompt_save_running_session(self, quitapp=False):
        """
        Prompt use to stop running session before application is closed

        :return: nothing
        """
        logging.info(
            "menuaction.py: clean_nodes_links_and_set_configuration() Exiting the program"
        )
        try:
            if not self.app.core.is_runtime():
                self.app.core.delete_session()
                if quitapp:
                    self.app.quit()
            else:
                result = messagebox.askyesnocancel("stop", "Stop the running session?")
                if result:
                    self.app.statusbar.progress_bar.start(5)
                    thread = threading.Thread(
                        target=self.cleanup_old_session, args=([quitapp])
                    )
                    thread.daemon = True
                    thread.start()
                elif quitapp:
                    self.app.quit()
        except grpc.RpcError:
            logging.exception("error deleting session")
            if quitapp:
                self.app.quit()

    def on_quit(self, event=None):
        """
        Prompt user whether so save running session, and then close the application

        :return: nothing
        """
        self.prompt_save_running_session(quitapp=True)

    def file_save_as_xml(self, event=None):
        logging.info("menuaction.py file_save_as_xml()")
        file_path = filedialog.asksaveasfilename(
            initialdir=str(XMLS_PATH),
            title="Save As",
            filetypes=(("EmulationScript XML files", "*.xml"), ("All files", "*")),
            defaultextension=".xml",
        )
        if file_path:
            self.app.core.save_xml(file_path)

    def file_open_xml(self, event=None):
        logging.info("menuaction.py file_open_xml()")
        file_path = filedialog.askopenfilename(
            initialdir=str(XMLS_PATH),
            title="Open",
            filetypes=(("XML Files", "*.xml"), ("All Files", "*")),
        )
        if file_path:
            logging.info("opening xml: %s", file_path)
            self.prompt_save_running_session()
            self.app.statusbar.progress_bar.start(5)
            thread = threading.Thread(target=self.app.core.open_xml, args=([file_path]))
            thread.start()

    def gui_preferences(self):
        dialog = PreferencesDialog(self.app, self.app)
        dialog.show()

    def canvas_size_and_scale(self):
        dialog = SizeAndScaleDialog(self.app, self.app)
        dialog.show()

    def canvas_set_wallpaper(self):
        dialog = CanvasWallpaperDialog(self.app, self.app)
        dialog.show()

    def help_core_github(self):
        webbrowser.open_new("https://github.com/coreemu/core")

    def help_core_documentation(self):
        webbrowser.open_new("http://coreemu.github.io/core/")

    def session_options(self):
        logging.debug("Click session options")
        dialog = SessionOptionsDialog(self.app, self.app)
        dialog.show()

    def session_change_sessions(self):
        logging.debug("Click session change sessions")
        dialog = SessionsDialog(self.app, self.app)
        dialog.show()

    def session_hooks(self):
        logging.debug("Click session hooks")
        dialog = HooksDialog(self.app, self.app)
        dialog.show()

    def session_servers(self):
        logging.debug("Click session emulation servers")
        dialog = ServersDialog(self.app, self.app)
        dialog.show()

    def edit_observer_widgets(self):
        dialog = ObserverDialog(self.app, self.app)
        dialog.show()

    def show_about(self):
        dialog = AboutDialog(self.app, self.app)
        dialog.show()

    def throughput(self):
        if not self.app.core.handling_throughputs:
            self.app.core.enable_throughputs()
        else:
            self.app.core.cancel_throughputs()
