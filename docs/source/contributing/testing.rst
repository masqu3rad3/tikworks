Testing
=======

Tests run against real Maya. There are no fake backends and no mocked scene:
``pytest`` runs under ``mayapy``, Maya's own interpreter, with Maya standalone
initialised once per session by ``tests/conftest.py``. Mocking is a last resort
and has to be justified in a comment.

Running the tests
-----------------

From the repository root, with ``mayapy`` on your ``PATH``:

.. tab-set::

   .. tab-item:: Unix / macOS

      .. code-block:: console

         $ PYTHONPATH=src/python mayapy -m pytest tests/unit -q
         $ PYTHONPATH=src/python mayapy -m pytest tests/unit/test_plug.py -v
         $ make tests-unit           # the same, through the Makefile
         $ make tests-integration
         $ make tests                # both

   .. tab-item:: Windows (PowerShell)

      .. code-block:: powershell

         $env:PYTHONPATH="src/python"; mayapy -m pytest tests/unit -q
         $env:PYTHONPATH="src/python"; mayapy -m pytest tests/unit/test_plug.py -v
         $env:PYTHONPATH="src/python"; mayapy -m pytest tests/unit --cov=tik.maya --cov-report=term-missing

``PYTHONPATH`` must point at ``src/python``, the folder that *contains* ``tik``,
not at ``src``.

The Qt UI tests cannot run under Maya standalone, which cannot host a
``QApplication``. They run without Maya, against the stub guide scene in
``tests/ui/stub.py``:

.. code-block:: console

   $ TIK_TESTS_NO_MAYA=1 QT_QPA_PLATFORM=offscreen mayapy -m pytest tests/ui -q
   $ make tests-ui

Layout
------

.. list-table::
   :widths: 30 70

   * - ``tests/unit/``
     - One file per module: ``test_plug.py``, ``test_transform.py``,
       ``test_matrix_constraint.py``... tik.trigger tests carry a ``_trigger``
       suffix (``test_session_trigger.py``, ``test_reconcile_trigger.py``).
   * - ``tests/integration/trigger/``
     - End-to-end builds against a real scene: the arm module, the builder, the
       lockstep guarantees, session build and checkout, the limb, reach and
       twist systems, the module ground rules.
   * - ``tests/ui/``
     - The Qt tests: the pipeline view, the Guide Designer, the action bar, the
       form builder, menus, the snapshot dialog. ``stub.py`` is the Maya-free
       ``GuideScene`` stand-in they and the screenshot script share.
   * - ``tests/helpers/toy_modules.py``
     - Throwaway modules that exercise the pipeline without a real rig.
   * - ``tests/unit/test_import_boundaries.py``
     - Fails if ``tik.trigger.core`` ever imports Maya or Qt.

Conventions
-----------

- ``pytest`` only. Files ``test_*.py``, classes ``Test*``, functions ``test_*``.
- Prefer real Maya behaviour; build the nodes, read them back.
- Tests are deterministic and clean up after themselves. Use unique names, and
  reset scene state between tests that need a clean scene.
- Registry tests call ``clear_registries()`` in ``setup_method`` and
  ``teardown_method`` so test order cannot leak registrations.
- Removed tests are archived under ``tests/_archived/``, never deleted outright.

Coverage
--------

.. code-block:: console

   $ make tests-cov            # unit + integration, then a report

``AI/testing_rules.md`` in the repository holds the same rules in the form the
review applies them, including the per-test coverage helper.
