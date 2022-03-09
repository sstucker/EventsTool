from fbs_runtime.application_context.PyQt5 import ApplicationContext
import sys

from widgets import MainWindow


class _AppContext(ApplicationContext):

    def __init__(self):
        super().__init__()
        self.version = self.build_settings['version']
        self.name = self.build_settings['app_name']

        self.ui_resource_location = str(self.get_resource('ui'))
        self.config_resource_location = str(self.get_resource('configurations'))

        self.window = None

    def run(self):
        self.window = MainWindow()
        self.window.setWindowTitle(self.name + ' v' + self.version)
        self.window.resize(250, 150)
        self.window.show()

        return self.app.exec_()


# Module interface
AppContext = _AppContext()
ui_resource_location = AppContext.ui_resource_location
config_resource_location = AppContext.config_resource_location
run = AppContext.run
