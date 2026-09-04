"""SceneWatcher: relaunching the tool must not leave old watchers firing."""

from tik.shared.ui.scene_watcher import SceneWatcher


def make_watcher(seen, jobs):
    return SceneWatcher(
        seen.append,
        install_job=lambda event, callback: jobs.append(event) or len(jobs),
        kill_job=lambda job: jobs.pop() if jobs else None,
    )


def test_uninstall_all_stops_every_live_watcher():
    """An orphaned watcher keeps reacting to the scene with stale code."""
    jobs, seen = [], []
    first = make_watcher(seen, jobs)
    second = make_watcher(seen, jobs)
    first.install()
    second.install()
    assert first.jobs and second.jobs

    SceneWatcher.uninstall_all()

    assert first.jobs == [] and second.jobs == []


def test_a_watcher_that_was_never_installed_is_harmless():
    jobs, seen = [], []
    make_watcher(seen, jobs)
    SceneWatcher.uninstall_all()  # must not raise


def test_uninstalling_one_leaves_the_others_alone():
    jobs, seen = [], []
    first = make_watcher(seen, jobs)
    second = make_watcher(seen, jobs)
    first.install()
    second.install()
    first.uninstall()
    assert first.jobs == [] and second.jobs


def test_a_dead_watcher_drops_out_of_the_registry():
    """The registry must not keep watchers alive past their owner."""
    import gc

    jobs, seen = [], []
    watcher = make_watcher(seen, jobs)
    watcher.install()
    del watcher
    gc.collect()
    SceneWatcher.uninstall_all()  # must not raise on a collected watcher
