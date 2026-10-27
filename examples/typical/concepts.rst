Concepts
========

.. contents:: On this page
   :depth: 2

.. _worked-example:

Worked example
--------------

The cost is :math:`\Theta(n \log n)`.

Plain-text placeholders such as <character> and <frequency> must remain visible.

.. _labelled-paragraph:

This paragraph has its own explicit reference label.

See :ref:`the labelled paragraph <labelled-paragraph>`.

Footnotes work too [#]_.

.. [#] A footnote that must remain readable after conversion.

Multiple paragraphs in a definition
   A definition can have more than one paragraph.

   The second paragraph must remain a separate paragraph.

.. math::

   S(n) = \sum_{i=1}^{n} i = \frac{n(n+1)}{2}

.. note::

   A useful note with **emphasis** and a :doc:`practice link <nested/practice>`.

.. warning::

   Check the precondition before applying the algorithm.

.. code-block:: python

   def total(values):
       return sum(values)

Comparison
----------

.. list-table:: Two strategies
   :header-rows: 1

   * - Strategy
     - Cost
   * - Scan
     - :math:`O(n)`
   * - Sort
     - :math:`O(n \log n)`

.. include:: includes/shared.txt

See :term:`Invariant`, :ref:`worked-example`, or :doc:`nested/practice`.
