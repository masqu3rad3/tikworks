"""Tests for tik.shared.prefs page declarations, registry and Preferences."""

import pytest


@pytest.fixture
def clean_registry():
    """Give each test an empty page registry and restore it afterwards."""
    from tik.shared.prefs import registry

    saved = registry.pages()
    registry.clear_pages()
    yield registry
    registry.clear_pages()
    for page in saved:
        registry.register_page(page)


@pytest.fixture
def demo_pages(clean_registry):
    """Two registered pages covering ordering and every basic field type."""
    from tik.core.fields import BoolField, ChoiceField, FieldGroup, IntField
    from tik.shared.prefs import PrefPage, register_page

    @register_page
    class Beta(PrefPage):
        name, label, order = "beta", "Beta", 20

        mode = ChoiceField("fast", ["fast", "slow"], help="How hard to think about it.")

    @register_page
    class Alpha(PrefPage):
        name, label, order = "alpha", "Alpha", 10

        LOOK = FieldGroup("Look")

        enabled = BoolField(True, group=LOOK, help="Whether the thing is on.")
        count = IntField(3, min=1, max=10, group=LOOK, help="How many things.")

    return Alpha, Beta


class TestRegistry:
    """Pages register and come back in a stable order."""

    def test_pages_are_ordered_by_order_then_name(self, demo_pages):
        from tik.shared.prefs import registry

        assert [page.name for page in registry.pages()] == ["alpha", "beta"]

    def test_duplicate_name_raises(self, demo_pages):
        from tik.shared.prefs import PrefPage, register_page

        with pytest.raises(ValueError):

            @register_page
            class Clash(PrefPage):
                name, label, order = "alpha", "Clash", 99

    def test_page_without_name_raises(self, clean_registry):
        from tik.shared.prefs import PrefPage, register_page

        with pytest.raises(ValueError):

            @register_page
            class Nameless(PrefPage):
                label, order = "Nameless", 1


class TestPreferencesDefaults:
    """A fresh Preferences reports declared defaults and touches no disk."""

    def test_reads_declared_defaults(self, demo_pages, tmp_path):
        from tik.shared.prefs import Preferences, PrefStore, registry

        prefs = Preferences(PrefStore("demo", folder=tmp_path), registry.pages())
        assert prefs.alpha.count == 3
        assert prefs.beta.mode == "fast"

    def test_construction_writes_nothing(self, demo_pages, tmp_path):
        from tik.shared.prefs import Preferences, PrefStore, registry

        Preferences(PrefStore("demo", folder=tmp_path), registry.pages())
        assert list(tmp_path.iterdir()) == []

    def test_unknown_page_raises_attribute_error(self, demo_pages, tmp_path):
        from tik.shared.prefs import Preferences, PrefStore, registry

        prefs = Preferences(PrefStore("demo", folder=tmp_path), registry.pages())
        with pytest.raises(AttributeError):
            prefs.nonexistent


class TestPreferencesPersistence:
    """Values survive a save/load round trip."""

    def test_save_then_reload(self, demo_pages, tmp_path):
        from tik.shared.prefs import Preferences, PrefStore, registry

        store = PrefStore("demo", folder=tmp_path)
        prefs = Preferences(store, registry.pages())
        prefs.alpha.count = 7
        prefs.save()

        reloaded = Preferences(PrefStore("demo", folder=tmp_path), registry.pages())
        assert reloaded.alpha.count == 7

    def test_stored_file_uses_flat_dotted_keys(self, demo_pages, tmp_path):
        from tik.shared.prefs import Preferences, PrefStore, registry

        store = PrefStore("demo", folder=tmp_path)
        prefs = Preferences(store, registry.pages())
        prefs.alpha.count = 7
        prefs.save()
        assert store.read()["alpha.count"] == 7

    def test_unknown_stored_keys_are_ignored(self, demo_pages, tmp_path):
        from tik.shared.prefs import Preferences, PrefStore, registry

        store = PrefStore("demo", folder=tmp_path)
        store.write({"alpha.count": 5, "alpha.gone": 1, "ghost.key": 2})
        prefs = Preferences(store, registry.pages())
        assert prefs.alpha.count == 5

    def test_invalid_stored_value_falls_back_to_default(self, demo_pages, tmp_path):
        from tik.shared.prefs import Preferences, PrefStore, registry

        store = PrefStore("demo", folder=tmp_path)
        store.write({"alpha.count": 999})  # above max=10
        prefs = Preferences(store, registry.pages())
        assert prefs.alpha.count == 3


class TestSnapshotRestore:
    """Snapshot and restore are the dialog's Cancel."""

    def test_snapshot_covers_every_field(self, demo_pages, tmp_path):
        from tik.shared.prefs import Preferences, PrefStore, registry

        prefs = Preferences(PrefStore("demo", folder=tmp_path), registry.pages())
        assert set(prefs.snapshot()) == {"alpha.enabled", "alpha.count", "beta.mode"}

    def test_restore_puts_values_back(self, demo_pages, tmp_path):
        from tik.shared.prefs import Preferences, PrefStore, registry

        prefs = Preferences(PrefStore("demo", folder=tmp_path), registry.pages())
        before = prefs.snapshot()
        prefs.alpha.count = 9
        prefs.restore(before)
        assert prefs.alpha.count == 3

    def test_reset_page_restores_declared_defaults(self, demo_pages, tmp_path):
        from tik.shared.prefs import Preferences, PrefStore, registry

        prefs = Preferences(PrefStore("demo", folder=tmp_path), registry.pages())
        prefs.alpha.count = 9
        prefs.reset_page("alpha")
        assert prefs.alpha.count == 3


class TestFieldDiscipline:
    """Rules every page must follow, checked across the whole registry."""

    def test_every_field_declares_help(self, demo_pages):
        from tik.shared.prefs import registry

        missing = [
            f"{page.name}.{name}"
            for page in registry.pages()
            for name, field in page.fields().items()
            if not field.help
        ]
        assert missing == []
