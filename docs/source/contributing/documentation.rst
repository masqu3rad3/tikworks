Documentation
=============

The documentation is a Sphinx project in ``docs/``. Pages are written by hand in
reStructuredText; the :doc:`API reference </autoapi/index>` is generated from
the source by sphinx-autoapi on every build, and nothing under ``autoapi/`` is
checked in.

Building
--------

The build needs only Python, not Maya. Install the pinned requirements into a
virtual environment and run the Makefile:

.. code-block:: console

   $ python -m venv .venv && . .venv/bin/activate
   $ pip install -r docs/requirements.txt
   $ cd docs && make html              # -> docs/build/html/index.html

   $ sphinx-autobuild docs/source docs/build/html   # rebuild on save, from the repo root

Read the Docs builds from ``.readthedocs.yaml`` with the same requirements file.

The build is expected to finish **without warnings**. Run it with warnings
turned into errors before opening a pull request that touches the docs:

.. code-block:: console

   $ sphinx-build -W --keep-going -b html docs/source docs/build/html

Writing pages
-------------

- One idea per page, stated in the first paragraph. Say what the reader can do
  after reading it.
- Every code sample must run as written against the current source. When the
  API changes, the page changes in the same commit.
- Refer to code with roles, so the reference links resolve and the build catches
  renames: ``:class:`~tik.maya.core.plug.Plug```,
  ``:func:`~tik.maya.core.registry.resolve```.
- Prefer a short example over a long explanation, and a table over a list of
  sentences that all have the same shape.
- Use ``.. note::`` for things a reader would otherwise get wrong, and
  ``.. warning::`` for things that cost work when they go wrong. Do not use them
  for emphasis.

Screenshots
-----------

UI screenshots live in ``docs/source/_static/screenshots`` and are rendered by
a script, not taken by hand, so they can be regenerated whenever the UI changes:

.. code-block:: console

   $ pip install PySide6        # only for the screenshot run; Maya is not needed
   $ TIK_TESTS_NO_MAYA=1 QT_QPA_PLATFORM=offscreen python docs/screenshots/capture.py

The script builds the real Trigger widgets over the Maya-free ``StubScene`` from
``tests/ui``, fills a session with a few actions and modules, and grabs each
widget offscreen. Pictures that need a Maya viewport (guides, a built rig) are
written as labelled **placeholder** images by the same script, so pages never
show a broken figure. To replace one, capture the described view in Maya and
save it under the same file name; the ``PLACEHOLDERS`` table at the top of the
script lists what each should show.

Include a screenshot with the ``screenshot`` class so it gets the frame:

.. code-block:: rst

   .. figure:: /_static/screenshots/trigger_window_session.png
      :class: screenshot
      :alt: What the picture shows, for readers who cannot see it

      A one-sentence caption that says what to look at.

Docstrings
----------

Docstrings follow the Google style (``Args:``, ``Returns:``, ``Raises:``,
``Attributes:``), rendered by ``sphinx.ext.napoleon``. The build renders an
``Attributes:`` section as instance-variable fields, so dataclass fields and
their descriptions appear once. A ``.. note::`` or a code example in a docstring
shows up in the API reference unchanged.

Layout of the sources
---------------------

.. code-block:: text

   docs/source/
   ├── index.rst                 landing page; owns every toctree
   ├── getting_started/          installation
   ├── tik_maya/                 the tik.maya section, guides in guides/
   ├── tik_trigger/              the tik.trigger section, guides in guides/
   ├── architecture/             layering and the package map
   ├── contributing/             this page, the style guide, testing
   ├── reference/                the hand-written entry to the generated API pages
   ├── _static/                  logo, custom.css, screenshots/, shapes/
   └── conf.py
