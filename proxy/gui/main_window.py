import sys

from PyQt5.QtCore import QSettings
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QMenu
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QPushButton, QVBoxLayout, QMessageBox, \
    QFileDialog, QAction, QMenuBar
from proxy.gui.plugins import PLUGINS
from proxy.gui.plugins.plugin_registry import PluginRegistry
from proxy.gui.widgets.connection_config import ConnectionConfig
from proxy.gui.widgets.http_messages_tabs import HttpMessagesTabs
from proxy.gui.widgets.http_messages_tree_view import HttpMessagesTreeView
from proxy.gui.worker import Worker
from proxy.pipe.apipe import ProxyParameters
from proxy.pipe.communication import RequestResponse
from proxy.pipe.persistence import parse_message_pairs, serialize_message_pairs

from proxy.parser.http_parser import HttpMessage

DEFAULT_PARAMETERS = ProxyParameters("0.0.0.0", 8888, "www.httpwatch.com", 80)


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.plugin_registry = PluginRegistry()
        self.plugin_registry.plugins = PLUGINS

        self.setGeometry(300, 300, 750, 750)
        self.setWindowTitle('PyProxy')

        self.worker = Worker()

        self.settings = QSettings("settings.ini", QSettings.IniFormat)

        self.settings.beginGroup("window")
        if self.settings.value("geometry", None):
            self.restoreGeometry(self.settings.value("geometry"))
        self.settings.endGroup()

        self.plugin_registry.restore_settings(self.settings)

        self.initUI()

    def initUI(self):
        self.connection_config = ConnectionConfig(self)
        self.connection_config.changed.connect(self.worker.setParameters)
        self.connection_config.changed.connect(self.setParameters)
        self.connection_config.restoreSettings(self.settings, DEFAULT_PARAMETERS)

        self.startButton = QPushButton(QIcon.fromTheme("media-playback-start"), "Start")
        self.stopButton = QPushButton(QIcon.fromTheme("media-playback-stop"), "Stop")
        self.restartButton = QPushButton(QIcon.fromTheme("media-skip-backward"), "Restart")

        self.startButton.clicked.connect(self.onStartClicked)
        self.stopButton.clicked.connect(self.onStopClicked)
        self.restartButton.clicked.connect(self.onRestartClicked)
        self.worker.received.connect(self.onReceived)
        self.worker.error.connect(self.onError)
        self.worker.running_changed.connect(self.update_status)

        hbox = QHBoxLayout()
        hbox.addWidget(self.connection_config)
        hbox.addWidget(self.startButton)
        hbox.addWidget(self.stopButton)
        hbox.addWidget(self.restartButton)

        self.treeView = HttpMessagesTreeView(self.plugin_registry, self)
        self.treeView.selected.connect(self.onMessageSelected)

        self.tabs = HttpMessagesTabs(self.plugin_registry)

        vbox = QVBoxLayout()
        vbox.addLayout(hbox)
        vbox.addWidget(self.treeView)
        vbox.addWidget(self.tabs)

        self.setLayout(vbox)
        vbox.setMenuBar(self.createMenu(QMenuBar()))
        self.show()

        self.update_status(self.worker.status())
        self.onMessageSelected(None)

    def createMenu(self, mainMenu):
        #mainMenu = QMenuBar()
        #mainMenu.setNativeMenuBar(False)
        fileMenu = mainMenu.addMenu('&File')

        openAction = QAction('&Open', self)
        openAction.triggered.connect(self.onLoadClicked)
        fileMenu.addAction(openAction)

        saveAction = QAction('&Save', self)
        saveAction.triggered.connect(self.onSaveClicked)
        fileMenu.addAction(saveAction)

        fileMenu.addSeparator()

        exitAction = QAction('&Exit', self)
        exitAction.triggered.connect(self.onExit)
        fileMenu.addAction(exitAction)

        settignsMenu = mainMenu.addMenu('&Settings')
        for label, callback in self.plugin_registry.add_settings_menu():
            action = QAction(label, self)
            action.triggered.connect(self.getSettingsCallback(callback))
            settignsMenu.addAction(action)

        return mainMenu

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        self.createMenu(menu)
        menu.exec_(self.mapToGlobal(event.pos()))

    def getSettingsCallback(self, callback):
        def func():
            callback()
            self.treeView.refresh()

        return func

    def onStartClicked(self, event):
        self.worker.start()

    def onStopClicked(self, event):
        self.worker.stop()

    def onRestartClicked(self, event):
        self.worker.stop()
        self.treeView.clear()
        self.worker.start()

    def onSaveClicked(self, event):
        file_name = QFileDialog.getSaveFileName(self, 'Save HTTP messages', '.', filter='*.http')[0]
        if not file_name:
            return

        if not file_name.endswith(".http"):
            file_name += ".http"

        self.save(file_name)

    def onLoadClicked(self, event):
        file_name = QFileDialog.getOpenFileName(self, 'Save HTTP messages', '.', filter='*.http')[0]
        if file_name:
            self.load(file_name)

    def load(self, file_name):
        f = open(file_name, "rb")
        for pair in parse_message_pairs(f):
            self.onReceived(pair)
        f.close()

    def save(self, file_name):
        f = open(file_name, "wb")
        serialize_message_pairs(self.treeView.getAllMessagePairs(), f)
        f.close()

    def closeEvent(self, QCloseEvent):
        if self.worker.status():
            self.worker.stop()

        self.settings.beginGroup("window")
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.endGroup()

        self.connection_config.saveSettings(self.settings)
        self.plugin_registry.save_settings(self.settings)
        super().closeEvent(QCloseEvent)

    def onReceived(self, rr: RequestResponse):
        self.treeView.onRequestResponse(rr)

    def onError(self, e: Exception):
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Critical)
        msg.setText("There was an error:")
        msg.setInformativeText(str(e))
        msg.setWindowTitle("Error")
        msg.exec_()

    def onMessageSelected(self, message: HttpMessage):
        self.tabs.onMessageSelected(message)

    def update_status(self, status):
        self.startButton.setDisabled(status)
        self.stopButton.setDisabled(not status)
        self.restartButton.setDisabled(not status)
        # self.requestButton.setDisabled(not status)

    def setParameters(self, parameters):
        self.plugin_registry.parameters = parameters

    def onExit(self, event):
        sys.exit()
