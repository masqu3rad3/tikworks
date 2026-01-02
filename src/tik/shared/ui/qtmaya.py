"""Maya specific UI/QT related functions"""

from maya import OpenMayaUI
from tik.shared.ui.Qt import QtWidgets, QtCompat


def get_main_window():
    """Get the memory adress of the main window to connect Qt dialog to it.
    Returns:
        (long or int) Memory Adress
    """
    win = OpenMayaUI.MQtUtil.mainWindow()
    ptr = QtCompat.wrapInstance(int(win), QtWidgets.QMainWindow)
    return ptr