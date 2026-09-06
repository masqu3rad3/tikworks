"""Two-way binding between Maya attributes and Qt widgets.

``binding.py`` grew an *adapter* seam precisely so the binders could be tested
without a scene, but nothing had ever used it -- the module sat at 61%, with
every widget mapping, the ``bind()`` dispatch and the whole ``BindingManager``
unexercised. These tests drive it through a fake adapter, and drive
``MayaAttributeAdapter`` itself through a fake ``maya.cmds``.
"""

from __future__ import annotations

import sys
import types

import pytest

from tik.shared.ui.binding import (
    Binder,
    BindingManager,
    CheckBoxBinder,
    ComboBinder,
    DoubleSpinnerBinder,
    IntSpinnerBinder,
    LineEditBinder,
    MayaAttributeAdapter,
    SliderBinder,
    bind,
)
from tik.shared.ui.Qt import QtWidgets

#: Every test below keeps its binder in a local. That is not tidiness: Qt holds
#: bound-method slots *weakly*, so a binder left as a temporary is collected the
#: moment ``start()`` returns and its widget connection dies with it -- which
#: makes a "nothing was written" assertion pass for the wrong reason.


class FakeAdapter:
    """Stands in for one Maya plug: a value, a presence flag, one observer."""

    def __init__(self, value=0, exists=True, plug_path="node.attr"):
        self.plug_path = plug_path
        self.value = value
        self._exists = exists
        self.callback = None
        self.writes: list = []
        self.unobserved = 0

    def exists(self):
        return self._exists

    def get(self):
        return self.value

    def set(self, value):
        self.value = value
        self.writes.append(value)

    def observe(self, callback):
        self.callback = callback

    def unobserve(self):
        self.callback = None
        self.unobserved += 1

    def change(self, value):
        """The scene moved: write the value and fire the observer, as Maya would."""
        self.value = value
        if self.callback is not None:
            self.callback()


@pytest.fixture
def spin(qapp):
    return QtWidgets.QSpinBox()


# --------------------------------------------------------------- mappings
#: ``(widget factory, binder, plug value, what the widget should show,
#:   what the user does, what should reach the plug)``
MAPPINGS = [
    (QtWidgets.QSpinBox, IntSpinnerBinder, 7, 7, lambda w: w.setValue(9), 9),
    (
        QtWidgets.QDoubleSpinBox,
        DoubleSpinnerBinder,
        1.5,
        1.5,
        lambda w: w.setValue(2.25),
        2.25,
    ),
    (
        QtWidgets.QCheckBox,
        CheckBoxBinder,
        True,
        True,
        lambda w: w.setChecked(False),
        False,
    ),
    (
        QtWidgets.QLineEdit,
        LineEditBinder,
        "hip",
        "hip",
        lambda w: w.setText("knee"),
        "knee",
    ),
]


@pytest.mark.parametrize(
    "widget_cls,binder_cls,plug_value,shown,edit,written",
    MAPPINGS,
    ids=[m[1].__name__ for m in MAPPINGS],
)
class TestWidgetMappings:
    """Each binder maps its own widget type in both directions."""

    def test_the_plug_value_reaches_the_widget(
        self, qapp, widget_cls, binder_cls, plug_value, shown, edit, written
    ):
        widget = widget_cls()
        binder = binder_cls(FakeAdapter(plug_value), widget)

        binder.start()

        assert binder.widget_value() == shown

    def test_an_edit_reaches_the_plug(
        self, qapp, widget_cls, binder_cls, plug_value, shown, edit, written
    ):
        widget = widget_cls()
        adapter = FakeAdapter(plug_value)
        binder = binder_cls(adapter, widget)
        binder.start()

        edit(widget)
        if isinstance(widget, QtWidgets.QLineEdit):
            widget.editingFinished.emit()

        assert adapter.value == written


def test_a_combo_binds_the_selected_index(qapp):
    combo = QtWidgets.QComboBox()
    combo.addItems(["ik", "fk", "both"])
    adapter = FakeAdapter(2)
    binder = ComboBinder(adapter, combo)
    binder.start()

    assert combo.currentIndex() == 2

    combo.setCurrentIndex(1)
    assert adapter.value == 1


class TestSliderScale:
    """A slider is integral; ``scale`` is how it carries a float plug."""

    def test_the_plug_value_is_scaled_onto_the_slider(self, qapp):
        slider = QtWidgets.QSlider()
        SliderBinder(FakeAdapter(0.75), slider, scale=100.0).start()

        assert slider.value() == 75

    def test_the_slider_position_is_unscaled_back_to_the_plug(self, qapp):
        slider = QtWidgets.QSlider()
        adapter = FakeAdapter(0.0)
        binder = SliderBinder(adapter, slider, scale=100.0)
        binder.start()

        slider.setValue(25)

        assert adapter.value == pytest.approx(0.25)

    def test_the_default_scale_is_one_to_one(self, qapp):
        slider = QtWidgets.QSlider()
        SliderBinder(FakeAdapter(30), slider).start()

        assert slider.value() == 30


class TestLifecycle:
    """``start`` / ``stop``, and what a missing plug does."""

    def test_a_missing_plug_disables_the_widget(self, spin):
        binder = IntSpinnerBinder(FakeAdapter(exists=False), spin)

        assert binder.start() is False
        assert not spin.isEnabled()
        assert not binder.active

    def test_a_present_plug_enables_the_widget(self, spin):
        binder = IntSpinnerBinder(FakeAdapter(3), spin)

        assert binder.start() is True
        assert spin.isEnabled()
        assert binder.active

    def test_a_widget_disabled_by_a_missing_plug_is_re_enabled_when_it_appears(
        self, spin
    ):
        adapter = FakeAdapter(3, exists=False)
        binder = IntSpinnerBinder(adapter, spin)
        binder.start()

        adapter._exists = True
        binder.start()

        assert spin.isEnabled() and binder.active

    def test_stop_releases_the_observer_and_the_signal(self, spin):
        adapter = FakeAdapter(3)
        binder = IntSpinnerBinder(adapter, spin)
        binder.start()

        binder.stop()

        assert not binder.active
        assert adapter.callback is None
        spin.setValue(11)
        assert adapter.value == 3

    def test_stopping_twice_is_harmless(self, spin):
        """Qt raises when a signal is disconnected twice; the binder swallows it."""
        binder = IntSpinnerBinder(FakeAdapter(3), spin)
        binder.start()

        binder.stop()
        binder.stop()

        assert not binder.active

    def test_stopping_one_that_never_started_is_harmless(self, spin):
        IntSpinnerBinder(FakeAdapter(3), spin).stop()

    def test_the_plug_path_is_exposed(self, spin):
        binder = IntSpinnerBinder(FakeAdapter(plug_path="L_arm.twist"), spin)

        assert binder.plug_path == "L_arm.twist"

    def test_an_adapter_without_a_path_reports_an_empty_one(self, spin):
        adapter = FakeAdapter()
        del adapter.plug_path

        assert IntSpinnerBinder(adapter, spin).plug_path == ""

    def test_an_unknown_direction_is_rejected(self, spin):
        with pytest.raises(ValueError, match="direction must be"):
            IntSpinnerBinder(FakeAdapter(), spin, direction="sideways")

    def test_the_base_binder_maps_nothing(self, spin):
        """``Binder`` is abstract: a subclass must supply all three mappings."""
        binder = Binder(FakeAdapter(), spin)

        for call in (binder.widget_value, binder.widget_signal):
            with pytest.raises(NotImplementedError):
                call()
        with pytest.raises(NotImplementedError):
            binder.set_widget_value(1)


class TestDirection:
    """``to_widget`` and ``to_maya`` are one-way; ``both`` is the default."""

    def test_to_widget_does_not_write_back(self, spin):
        adapter = FakeAdapter(3)
        binder = IntSpinnerBinder(adapter, spin, direction="to_widget")
        binder.start()

        spin.setValue(9)

        assert adapter.writes == []

    def test_to_widget_still_follows_the_plug(self, spin):
        adapter = FakeAdapter(3)
        binder = IntSpinnerBinder(adapter, spin, direction="to_widget")
        binder.start()

        adapter.change(12)

        assert spin.value() == 12

    def test_to_maya_does_not_observe_the_plug(self, spin):
        adapter = FakeAdapter(3)
        binder = IntSpinnerBinder(adapter, spin, direction="to_maya")
        binder.start()

        assert adapter.callback is None

    def test_to_maya_still_writes_edits(self, spin):
        adapter = FakeAdapter(3)
        binder = IntSpinnerBinder(adapter, spin, direction="to_maya")
        binder.start()

        spin.setValue(9)

        assert adapter.value == 9


class TestEchoSuppression:
    """The two directions must not feed each other in a loop."""

    def test_a_plug_change_does_not_echo_back_as_a_write(self, spin):
        adapter = FakeAdapter(3)
        binder = IntSpinnerBinder(adapter, spin)
        binder.start()
        adapter.writes.clear()

        adapter.change(12)

        assert spin.value() == 12
        assert adapter.writes == []

    def test_a_failing_write_is_logged_and_does_not_escape(self, spin, caplog):
        """A dead plug must not take the whole panel down with it."""
        adapter = FakeAdapter(3, plug_path="gone.attr")
        adapter.set = _raise
        binder = IntSpinnerBinder(adapter, spin)
        binder.start()

        spin.setValue(9)

        assert "gone.attr" in caplog.text

    def test_a_vanished_plug_is_not_read(self, spin):
        adapter = FakeAdapter(3)
        binder = IntSpinnerBinder(adapter, spin)
        binder.start()
        spin.setValue(5)

        adapter._exists = False
        adapter.value = 99
        binder.update_widget()

        assert spin.value() == 5


def _raise(_value):
    raise RuntimeError("plug is gone")


class TestBindDispatch:
    """``bind()`` picks the binder from the widget type."""

    @pytest.mark.parametrize(
        "widget_cls,expected",
        [
            (QtWidgets.QSpinBox, IntSpinnerBinder),
            (QtWidgets.QDoubleSpinBox, DoubleSpinnerBinder),
            (QtWidgets.QCheckBox, CheckBoxBinder),
            (QtWidgets.QComboBox, ComboBinder),
            (QtWidgets.QSlider, SliderBinder),
            (QtWidgets.QLineEdit, LineEditBinder),
        ],
        ids=lambda value: getattr(value, "__name__", value),
    )
    def test_each_widget_type_gets_its_binder(self, qapp, widget_cls, expected):
        assert type(bind("node.attr", widget_cls(), adapter=FakeAdapter())) is expected

    def test_a_double_spin_box_does_not_fall_through_to_the_int_binder(self, qapp):
        """``QDoubleSpinBox`` is not a ``QSpinBox``, but order still matters here."""
        binder = bind("node.attr", QtWidgets.QDoubleSpinBox(), adapter=FakeAdapter(1.5))

        assert binder.widget_value() == pytest.approx(0.0)
        assert isinstance(binder.widget_value(), float)

    def test_an_unsupported_widget_is_rejected(self, qapp):
        with pytest.raises(TypeError, match="No binder for widget type QLabel"):
            bind("node.attr", QtWidgets.QLabel(), adapter=FakeAdapter())

    def test_the_binder_is_not_started_yet(self, qapp):
        assert (
            bind("node.attr", QtWidgets.QSpinBox(), adapter=FakeAdapter()).active
            is False
        )

    def test_the_direction_is_passed_through(self, qapp):
        binder = bind(
            "node.attr",
            QtWidgets.QSpinBox(),
            direction="to_widget",
            adapter=FakeAdapter(),
        )

        assert binder.direction == "to_widget"

    def test_without_an_adapter_a_maya_one_is_built_from_the_path(self, qapp):
        binder = bind("L_arm.twist", QtWidgets.QSpinBox())

        assert isinstance(binder.adapter, MayaAttributeAdapter)
        assert binder.adapter.plug_path == "L_arm.twist"


class TestBindingManager:
    """The manager owns binders and retries the ones whose plug is missing."""

    def test_adding_starts_the_binder(self, spin):
        manager = BindingManager()

        binder = manager.add(IntSpinnerBinder(FakeAdapter(3), spin))

        assert binder.active and len(manager) == 1

    def test_removing_stops_and_forgets(self, spin):
        manager = BindingManager()
        binder = manager.add(IntSpinnerBinder(FakeAdapter(3), spin))

        manager.remove(binder)

        assert not binder.active and len(manager) == 0

    def test_removing_one_it_never_held_is_harmless(self, spin):
        manager = BindingManager()

        manager.remove(IntSpinnerBinder(FakeAdapter(3), spin))

        assert len(manager) == 0

    def test_clear_stops_everything(self, qapp):
        manager = BindingManager()
        binders = [
            manager.add(IntSpinnerBinder(FakeAdapter(3), QtWidgets.QSpinBox()))
            for _ in range(3)
        ]

        manager.clear()

        assert len(manager) == 0
        assert not any(binder.active for binder in binders)

    def test_update_all_refreshes_the_active_widgets(self, qapp):
        manager = BindingManager()
        widgets = [QtWidgets.QSpinBox() for _ in range(2)]
        adapters = [FakeAdapter(1), FakeAdapter(2)]
        for adapter, widget in zip(adapters, widgets):
            manager.add(IntSpinnerBinder(adapter, widget))

        for adapter in adapters:
            adapter.value += 10
        manager.update_all()

        assert [widget.value() for widget in widgets] == [11, 12]

    def test_update_all_skips_the_inactive(self, spin):
        manager = BindingManager()
        manager.add(IntSpinnerBinder(FakeAdapter(3, exists=False), spin))

        manager.update_all()

        assert spin.value() == 0

    def test_a_missing_plug_starts_the_retry_timer(self, spin):
        manager = BindingManager(poll_interval_ms=10)

        manager.add(IntSpinnerBinder(FakeAdapter(exists=False), spin))

        assert manager._timer is not None and manager._timer.isActive()

    def test_a_present_plug_needs_no_timer(self, spin):
        manager = BindingManager()

        manager.add(IntSpinnerBinder(FakeAdapter(3), spin))

        assert manager._timer is None

    def test_reconnect_reports_what_is_still_missing(self, qapp):
        manager = BindingManager()
        here = FakeAdapter(3)
        gone = FakeAdapter(exists=False)
        manager.add(IntSpinnerBinder(here, QtWidgets.QSpinBox()))
        manager.add(IntSpinnerBinder(gone, QtWidgets.QSpinBox()))

        assert manager.reconnect() == 1

    def test_reconnect_picks_up_a_plug_that_has_appeared(self, spin):
        manager = BindingManager(poll_interval_ms=10)
        adapter = FakeAdapter(4, exists=False)
        binder = manager.add(IntSpinnerBinder(adapter, spin))

        adapter._exists = True

        assert manager.reconnect() == 0
        assert binder.active and spin.value() == 4

    def test_the_timer_stops_once_everything_is_connected(self, spin):
        manager = BindingManager(poll_interval_ms=10)
        adapter = FakeAdapter(4, exists=False)
        manager.add(IntSpinnerBinder(adapter, spin))

        adapter._exists = True
        manager.reconnect()

        assert not manager._timer.isActive()

    def test_clearing_stops_the_timer(self, spin):
        manager = BindingManager(poll_interval_ms=10)
        manager.add(IntSpinnerBinder(FakeAdapter(exists=False), spin))

        manager.clear()

        assert not manager._timer.isActive()


@pytest.fixture
def fake_cmds(monkeypatch):
    """A stand-in ``maya.cmds`` -- ``MayaAttributeAdapter`` imports it lazily."""

    class Cmds:
        def __init__(self):
            self.attrs = {"node.attr": 1.0}
            self.set_calls: list = []
            self.jobs: dict = {}
            self.killed: list = []
            self._next = 100

        def objExists(self, path):  # noqa: N802 - mirrors maya.cmds
            return path in self.attrs

        def getAttr(self, path):  # noqa: N802
            return self.attrs[path]

        def setAttr(self, path, value, **kwargs):  # noqa: N802
            self.attrs[path] = value
            self.set_calls.append((path, value, kwargs))

        def scriptJob(self, **kwargs):  # noqa: N802
            if "attributeChange" in kwargs:
                self._next += 1
                self.jobs[self._next] = kwargs["attributeChange"]
                return self._next
            if "exists" in kwargs:
                return kwargs["exists"] in self.jobs
            if "kill" in kwargs:
                self.killed.append(kwargs["kill"])
                self.jobs.pop(kwargs["kill"], None)
                return None
            raise AssertionError(f"unexpected scriptJob {kwargs}")

    cmds = Cmds()
    maya = sys.modules.get("maya") or types.ModuleType("maya")
    monkeypatch.setitem(sys.modules, "maya", maya)
    monkeypatch.setattr(maya, "cmds", cmds, raising=False)
    monkeypatch.setitem(sys.modules, "maya.cmds", cmds)
    return cmds


class TestMayaAttributeAdapter:
    """The default adapter, against a fake ``cmds``."""

    def test_it_reports_whether_the_plug_is_there(self, fake_cmds):
        assert MayaAttributeAdapter("node.attr").exists()
        assert not MayaAttributeAdapter("gone.attr").exists()

    def test_it_reads_the_plug(self, fake_cmds):
        assert MayaAttributeAdapter("node.attr").get() == 1.0

    def test_it_writes_a_number_plainly(self, fake_cmds):
        MayaAttributeAdapter("node.attr").set(4.0)

        assert fake_cmds.set_calls == [("node.attr", 4.0, {})]

    def test_a_string_needs_the_typed_setattr(self, fake_cmds):
        """``cmds.setAttr`` silently misreads a string without ``type="string"``."""
        MayaAttributeAdapter("node.name").set("hip")

        assert fake_cmds.set_calls == [("node.name", "hip", {"type": "string"})]

    def test_observing_registers_a_script_job(self, fake_cmds):
        adapter = MayaAttributeAdapter("node.attr")
        calls: list = []

        adapter.observe(lambda: calls.append(1))

        assert fake_cmds.jobs[adapter._job][0] == "node.attr"
        fake_cmds.jobs[adapter._job][1]()
        assert calls == [1]

    def test_observing_twice_replaces_the_first_job(self, fake_cmds):
        adapter = MayaAttributeAdapter("node.attr")
        adapter.observe(lambda: None)
        first = adapter._job

        adapter.observe(lambda: None)

        assert fake_cmds.killed == [first]
        assert adapter._job != first

    def test_unobserving_kills_the_job(self, fake_cmds):
        adapter = MayaAttributeAdapter("node.attr")
        adapter.observe(lambda: None)
        job = adapter._job

        adapter.unobserve()

        assert fake_cmds.killed == [job]
        assert adapter._job is None

    def test_unobserving_without_a_job_is_harmless(self, fake_cmds):
        MayaAttributeAdapter("node.attr").unobserve()

        assert fake_cmds.killed == []

    def test_a_job_maya_already_dropped_is_forgotten_quietly(self, fake_cmds):
        """Reopening a scene kills script jobs behind our back."""
        adapter = MayaAttributeAdapter("node.attr")
        adapter.observe(lambda: None)
        fake_cmds.jobs.clear()

        adapter.unobserve()

        assert adapter._job is None
        assert fake_cmds.killed == []

    def test_a_raising_script_job_query_is_swallowed(self, fake_cmds, monkeypatch):
        adapter = MayaAttributeAdapter("node.attr")
        adapter.observe(lambda: None)
        monkeypatch.setattr(fake_cmds, "scriptJob", _raise_runtime)

        adapter.unobserve()

        assert adapter._job is None


def _raise_runtime(*_args, **_kwargs):
    raise RuntimeError("no such job")
