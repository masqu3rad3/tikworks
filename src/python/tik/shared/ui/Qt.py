"""Single import point for Qt inside tikworks (re-exports the vendored shim)."""

from tik.vendor.Qt import QtCompat, QtCore, QtGui, QtWidgets, __binding__  # noqa: F401

__all__ = ["QtCompat", "QtCore", "QtGui", "QtWidgets", "__binding__"]
