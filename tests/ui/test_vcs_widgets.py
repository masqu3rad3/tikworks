"""The shared widgets only know they have a second button and a clickable field."""

from tik.core.fields import FileField, Schema
from tik.shared.ui.fields import FormBuilder
from tik.shared.ui.Qt import QtCore, QtGui, QtWidgets
from tik.shared.ui.status import StatusFields
from tik.shared.ui.versioned_field import VersionedFileField


class Settings(Schema):
    script = FileField("", extensions=[".py"], kind="script")


def test_versioned_field_has_no_vcs_button_by_default(qapp):
    field = VersionedFileField([".py"])
    assert field.vcs_button is None


def test_versioned_field_vcs_button_calls_back_with_the_widget(qapp):
    seen = []
    field = VersionedFileField([".py"], vcs=("From Tik Manager", seen.append))
    assert field.vcs_button.toolTip() == "From Tik Manager"
    assert field.vcs_button.objectName() == "VcsButton"
    field.vcs_button.click()
    assert seen == [field]


def test_form_builder_passes_field_name_and_field_to_the_handler(qapp):
    seen = []
    form = FormBuilder(
        Settings(),
        file_vcs=(
            "From Tik Manager",
            lambda name, field, widget: seen.append((name, field.kind, widget)),
        ),
    )
    widget = form.widget("script")
    widget.vcs_button.click()
    assert seen[0][:2] == ("script", "script") and seen[0][2] is widget


def test_status_field_click_and_color(qapp):
    strip = QtWidgets.QWidget()
    status = StatusFields(strip, ("vcs",))
    seen = []
    status.set_click("vcs", lambda: seen.append("clicked"))
    status.set_color("vcs", "#f0b45c")
    assert "#f0b45c" in status.labels["vcs"].styleSheet()
    QtWidgets.QApplication.sendEvent(
        status.labels["vcs"],
        QtGui.QMouseEvent(
            QtCore.QEvent.MouseButtonPress,
            QtCore.QPointF(1, 1),
            QtCore.Qt.LeftButton,
            QtCore.Qt.LeftButton,
            QtCore.Qt.NoModifier,
        ),
    )
    assert seen == ["clicked"]
    status.set_color("vcs", "")
    assert status.labels["vcs"].styleSheet() == ""
