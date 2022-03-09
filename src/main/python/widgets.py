import json
import os
import warnings
from threading import Thread

import numpy as np
import pyqtgraph
from PyQt5 import uic
from PyQt5.QtCore import pyqtSignal, QTimer
from PyQt5.QtWidgets import QWidget, QLayout, QGridLayout, QGroupBox, QMainWindow, QSpinBox, QDoubleSpinBox, QCheckBox, \
    QRadioButton, \
    QFileDialog, QMessageBox, QLineEdit, QTextEdit, QComboBox, QDialog, QFrame, QTableWidget, QTableWidgetItem
import StimTool

from Events import *
from JsonModel import JsonModel


def replaceWidget(old_widget: QWidget, new_widget: QWidget):
    """Replace a widget with another."""
    plotwidget_placeholder_layout = old_widget.parent().layout()
    plotwidget_placeholder_layout.replaceWidget(old_widget, new_widget)
    new_widget.setObjectName(old_widget.objectName())
    old_widget.hide()
    new_widget.show()
    old_widget.parentWidget().__dict__[old_widget.objectName()] = new_widget  # Goodbye, old widget reference!


class UiWidget:

    def __init__(self, uiname: str = None):
        """Base class for QWidget or QObject that uses a Qt Creator ui file.

        Automatically loads the .ui file with the same name as the class. Provides convenience function 'replaceWidget'
        for dynamically replacing placeholder Widgets in the .ui file.

        Args:
            uiname (str): Optional kwarg. The .ui file to load from. Must be located in src/main/ui folder relative to project
                directory. If not provided, .ui file is assumed to be same as the class.
        """
        super().__init__()

        # by default, load .ui file of the same name as the class
        if uiname is None:
            uiname = self.__class__.__name__
        ui = os.sep.join([StimTool.ui_resource_location, uiname + '.ui'])
        uic.loadUi(ui, self)

    def loadStateFromJson(self, statefile: str):
        with open(statefile, 'r') as file:
            try:
                _undictize(self, json.load(file)[self.objectName()])
            except KeyError:
                raise ValueError(self.__class__.__name__
                                 + " instance named '" + self.objectName()
                                 + "' not found the root of state file " + statefile)

    def writeStateToJson(self, statefile: str):
        with open(statefile, 'w') as file:
            json.dump({self.objectName(): _dictize(self)}, file, indent=4)


# These Widget types will be dictized and undictized by the functions below
DICTABLE_TYPES = [
    QComboBox,
    QSpinBox,
    QDoubleSpinBox,
    QCheckBox,
    QRadioButton,
    QLineEdit,
    QTextEdit,
]


def _undictize(obj, dictionary: dict):
    """Read values and states of QWidgets from a nested dictionary of object names.

    Recurses over entire dictionary tree, assigning values to children of obj.

    Args:
        obj (QWidget or QLayout): Qt Widget or Layout instance to serve as the root of the tree
        dictionary (dict): Dictionary with keys corresponding to children of obj
    """
    for key in dictionary.keys():
        try:
            child = getattr(obj, key)
        except AttributeError:  # For some reason, not all children are in __dict__
            child = None
            for c in obj.children():
                if key == c.objectName():
                    child = c
                    break
            if child is None:
                warnings.warn(key + ' not found in ' + obj.objectName())
                continue
        if type(child) in DICTABLE_TYPES:
            _set_widget_value(child, dictionary[key])
        else:
            _undictize(child, dictionary[key])


def _dictize(obj):
    """Convert a hierarchy of QWidgets and QLayouts to a dictionary.

    Recurses over entire tree given a root object. Will only assign a QWidget or QLayout's name and value to the dictionary
    if it is in DICTABLE_TYPES, therefore having behavior defined in _get_widget_value.

    Args:
        obj (QWidget or QLayout): Qt Widget or Layout instance to serve as the root of the tree
    """
    struct = {}
    for child in obj.children():
        if type(child) in DICTABLE_TYPES and not child.objectName().startswith('qt_'):
            struct[child.objectName()] = _get_widget_value(child)
        elif len(child.children()) > 0:
            # Recurse if children have dictable children
            s = _dictize(child)
            if len(s) > 0:
                struct[child.objectName()] = s
    return struct


def _get_widget_value(widget: QWidget):
    if type(widget) in [QCheckBox, QRadioButton]:
        return widget.isChecked()
    elif type(widget) in [QLineEdit, QTextEdit]:
        return widget.text()
    elif type(widget) in [QSpinBox, QDoubleSpinBox]:
        return widget.value()
    elif type(widget) in [QComboBox]:
        return widget.currentIndex()


def _set_widget_value(widget: QWidget, value):
    if type(widget) in [QCheckBox, QRadioButton]:
        widget.setChecked(value)
    elif type(widget) in [QLineEdit, QTextEdit]:
        widget.setText(value)
    elif type(widget) in [QSpinBox, QDoubleSpinBox]:
        widget.setValue(value)
    elif type(widget) in [QComboBox]:
        widget.setCurrentIndex(value)

# -- Widgets -----------------------------------------

class EventsTabWidget(QWidget, UiWidget):

    def __init__(self, name):
        super().__init__()
        self._name = name

        # --

        self._sidecar = JsonModel()
        self.treeViewSidecar.setModel(self._sidecar)
        with open('test/output/sub-01_task-tapping_events.json', 'r') as file:
            document = json.load(file)
            self._sidecar.load(document)
        self.treeViewSidecar.setAlternatingRowColors(True)
        self.treeViewSidecar.resize(500, 300)

        self._events = Events('test/output/sub-01_task-tapping_events.tsv')
        self.tableViewEvents.setRowCount(len(self._events.data))
        self.tableViewEvents.setColumnCount(len(self._events.data[0]))
        for i, row in enumerate(self._events.data):
            for j, element in enumerate(row):
                self.tableViewEvents.setItem(i, j, QTableWidgetItem(element))

    def _closed(self):
        print('Tab closed')

    @property
    def name(self):
        return self._name


class MainWindow(QMainWindow, UiWidget):

    def __init__(self):
        super().__init__()

        self.actionOpen_Events.triggered.connect(self._open_events)
        self.tabFiles.tabCloseRequested.connect(self._close_events)
        self.tabFiles.currentChanged.connect(self._tab_changed)

        # Close all tabs to begin with
        self._menubar_set_file_options_visible(False)
        while self.tabFiles.count() > 0:
            self.tabFiles.removeTab(0)

    def _tab_changed(self, index):

        if self.tabFiles.count() > 0 and type(self.tabFiles.currentWidget()) == EventsTabWidget:
            # Set the menu actions text to reflect selected Events
            name = self.tabFiles.currentWidget().name
            self.actionSave.setText("Save '{}'".format(name))
            self.actionSave_As.setText("Save '{}' As".format(name))
            self.actionExport_to_SNIRF.setText("Export '{}' to SNIRF".format(name))

    def _menubar_set_file_options_visible(self, visible):
        self.actionSave.setVisible(visible)
        self.actionSave_As.setVisible(visible)
        self.actionExport_to_SNIRF.setVisible(visible)

    def _open_events(self):
        name = 'sub-01_task-tapping_events'
        self.tabFiles.addTab(EventsTabWidget(name), name)
        self._menubar_set_file_options_visible(True)

    def _close_events(self, index):
        print('Closing', index)
        self.tabFiles.removeTab(index)
        if not self.tabFiles.count() > 0:
            self._menubar_set_file_options_visible(False)


    def loadConfiguration(self):
        file = QFileDialog.getOpenFileName(self, "Load Configuration File", StimTool.config_resource_location,
                                           "ui configuration file (*.uicfg)")[0]
        if os.path.exists(file):
            self.loadStateFromJson(file)

    def saveConfiguration(self):
        file = QFileDialog.getSaveFileName(self, "Save Configuration File", StimTool.config_resource_location,
                                           "ui configuration file (*.uicfg)")[0]
        if len(file) > 0:
            self.writeStateToJson(file)

    # Overload
    def closeEvent(self, event):
        quit_msg = "Are you sure you want to exit StimTool?"
        reply = QMessageBox.question(self, 'Message', quit_msg, QMessageBox.Yes, QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.writeStateToJson(os.path.join(StimTool.config_resource_location, '.last'))
            event.accept()
        else:
            event.ignore()
