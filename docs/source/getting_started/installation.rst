Installation
============

TikWorks is a plain Python package that runs inside Maya. There is nothing to
compile and nothing to ``pip install``: put one folder on Maya's Python path
and import it.

Requirements
------------

.. list-table::
   :widths: 30 70

   * - Autodesk Maya
     - 2024 or newer. The math nodes behind plug arithmetic differ between
       versions; tik.maya picks the right ones at runtime.
   * - Python
     - 3.10 or newer, which is what Maya 2024 and later ship.
   * - Qt
     - PySide2 or PySide6, whichever your Maya has. The vendored ``Qt.py`` shim
       hides the difference from the UI code.
   * - Third-party packages
     - None. TikWorks deliberately depends only on the standard library and on
       what Maya bundles.

Get the code
------------

Clone the repository, or download it as a zip and unpack it somewhere stable:

.. code-block:: console

   $ git clone https://github.com/masqu3rad3/tikworks.git

The importable package is ``tikworks/src/python/tik``. The path you need on
``sys.path`` is therefore ``.../tikworks/src/python``, not ``src``.

Tell Maya where it is
---------------------

Pick whichever fits how you work.

.. tab-set::

   .. tab-item:: In a Script Editor session

      .. code-block:: python

         import sys
         sys.path.insert(0, "/path/to/tikworks/src/python")

         import tik.maya as tm

   .. tab-item:: For every session (userSetup.py)

      Add the path in your ``userSetup.py`` (in ``~/maya/scripts`` or
      ``Documents/maya/scripts`` on Windows):

      .. code-block:: python

         import sys
         sys.path.append("/path/to/tikworks/src/python")

   .. tab-item:: Through the environment

      Add the folder to ``PYTHONPATH`` in your ``Maya.env`` or in the shell
      that launches Maya:

      .. code-block:: text

         PYTHONPATH = /path/to/tikworks/src/python

Check it works
--------------

In Maya's Script Editor:

.. code-block:: python

   import tik.maya as tm

   cube = tm.polyCube(name="hello")[0]      # any cmds command works through tm
   print(type(cube))                        # <class 'tik.maya.types.transform.Transform'>
   cube.translate = (0, 5, 0)

If ``type(cube)`` prints a tik.maya class rather than a string, the wrapper is
live. The :doc:`quickstart </tik_maya/quickstart>` continues from here.

For tik.trigger, open the tool window:

.. code-block:: python

   import tik.trigger.ui

   tik.trigger.ui.show()

The window docks like any Maya panel. :doc:`/tik_trigger/quickstart` walks
through a first build.

Running the tests
-----------------

Tests run under ``mayapy``, Maya's own interpreter, so they exercise real Maya
behaviour rather than mocks. From the repository root:

.. code-block:: console

   $ PYTHONPATH=src/python mayapy -m pytest tests/unit -q

:doc:`/contributing/testing` has the full layout and the Qt-only suite.
