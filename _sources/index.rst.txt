Sphinx plugin for Antlr4
========================

A4Doc is a sphinx plugin for documenting Antlr4 grammars.

It's primary target is to provide some overview for DSL users
(generated documentation may not include some nuances essential
for compiler developers).

See an example output: :a4:g:`Json`.

.. _features:

Features
--------

- A new domain with ``grammar`` and ``rule`` directives called ``a4``.

- Directives for rendering railroad diagrams, such as this one:

  .. railroad-diagram::
     - choice:
       - terminal: 'parser'
       -
       - terminal: 'lexer '
       default: 1
     - terminal: 'grammar'
     - non_terminal: 'identifier'
     - terminal: ';'

- Directive for extracting documentation comments and rendering docs and
  diagrams from ``.g4`` source files.

Requirements
------------

A4Doc uses dataclasses to represent parsed antlr files, thus ``python >= 3.7``
is required. Also, this extension requires ``sphinx >= 1.8.0`` because it
relies on some features added in that release.

Installation
------------

Install ``sphinx-a4doc`` with pip:

.. code-block:: sh

    pip3 install sphinx-a4doc

Add ``sphinx_a4doc`` to the list of extensions in your ``conf.py``.
If you intend to generate documentation from sources, also specify the
location of your grammar files:

.. code-block:: python

   extensions = [
       'sphinx_a4doc',
   ]

   # Assuming conf.py is in project/docs/source/conf.py
   # and grammars are in project/project/grammars
   from os.path import dirname
   a4_base_path = dirname(__file__) + '/../../project/grammars'

Quickstart
----------

Use the :rst:dir:`a4:grammar` directive to declare a new grammar.
Within the grammar block, use the :rst:dir:`a4:rule` to declare a new rule:

.. code-block:: rst

   .. a4:grammar:: MyGrammar

      A grammar for my DSL.

      .. a4:rule:: root

         The root grammar rule.

The above code produces this output:

.. highlights::

   .. a4:grammar:: MyGrammar

      A grammar for my DSL.

      .. a4:rule:: root

         The root grammar rule.

Use :rst:role:`a4:grammar` (or :rst:role:`a4:g` as a shortcut) or
:rst:role:`a4:rule` (or :rst:role:`a4:r`) roles to refer the declared
grammars and rules:

.. code-block:: rst

   Grammar :a4:g:`MyGrammar` has a root rule :a4:r:`MyGrammar.root`.

The above code produces this output:

.. highlights::

   Grammar :a4:g:`MyGrammar` has a root rule :a4:r:`MyGrammar.root`.

Use :rst:dir:`railroad-diagram`, :rst:dir:`lexer-rule-diagram` and
:rst:dir:`parser-rule-diagram` directives to render diagrams:

.. code-block:: rst

   .. parser-rule-diagram:: 'def' ID '(' (arg (',' arg)*)? ')' ':'

The above code produces this output:

.. highlights::

   .. parser-rule-diagram:: 'def' ID '(' (arg (',' arg)*)? ')' ':'

Use :rst:dir:`a4:autogrammar` directive to generate documentation
from a grammar file.

RST reference
-------------

Declaring objects
~~~~~~~~~~~~~~~~~

.. rst:autodirective:: .. a4:grammar:: name

.. rst:autodirective:: .. a4:rule:: name

Cross-referencing objects
~~~~~~~~~~~~~~~~~~~~~~~~~

.. rst:role:: any
   :noindex:

   All ``a4`` objects can be cross-referenced via the :rst:role:`any` role.

   If given a full path, e.g. ``:any:`grammar_name.rule_name```,
   :rst:role:`any` will search a rule called ``rule_name`` in the
   grammar called ``grammar_name`` and then, should this search fail, in all
   grammars that are imported from ``grammar_name``, recursively.

   If given a relative path, e.g. ``:any:`name```,
   :rst:role:`any` will perform a global search for a rule or a grammar with the
   corresponding name.

.. rst:role:: a4:grammar
              a4:g

   Cross-reference a grammar by its name.

   There's nothing special about this role, just specify the grammar name.

.. rst:role:: a4:rule
              a4:r

   Cross-reference a grammar by its name or full path.

   If given a full path, e.g. ``:a4:r:`grammar_name.rule_name```,
   the rule will be first searched in the corresponding grammar, then in
   all imported grammars, recursively.

   If given a rule name only, e.g. ``:a4:r:`rule_name```, the behavior depends
   on context:

   - when used in a grammar declaration body, the rule will be first searched
     in that grammar, then in any imported grammar, and at last, in the default
     grammar.

   - when used without context, the rule will only be searched
     in the default grammar.

   Prepending full path with a tilde works as expected.

Rendering diagrams
~~~~~~~~~~~~~~~~~~

.. rst:autodirective:: railroad-diagram

.. rst:autodirective:: lexer-rule-diagram
   :no-options:

.. rst:autodirective:: parser-rule-diagram
   :no-options:

Autodoc directive
~~~~~~~~~~~~~~~~~

.. rst:autodirective:: .. a4:autogrammar:: filename
   :no-inherited-options:
   :no-options-header:

.. rst:autodirective:: .. a4:autorule:: filename rulename
   :no-inherited-options:
   :no-options-header:

.. rst:autodirective:: docstring-marker

.. rst:autodirective:: members-marker

.. _grammar_comments:

Grammar comments and annotations
--------------------------------

The :rst:dir:`a4:autogrammar` directive does not parse any comment that's found
in a grammar file. Instead, it searches for 'documentation' comments, i.e. ones
specially formatted. There are three types of such comments:

- documentation comments are multiline comments that start with ``/**``
  (that is, a slash followed by double asterisk). These comments should contain
  valid rst-formatted text.

  It is common to outline documentation comments by adding an asterisk on each
  row. Though this is completely optional, a4doc can recognize and handle
  this pattern.

  Example:

  .. code-block:: antlr

     /**
      * This is the grammar root.
      */
     module: moduleItem* EOF

- control comments are inline comments that start with ``//@``. Control
  comments contain special commands that affect rendering process.

  Example:

  .. code-block:: antlr

     //@ doc:no-diagram
     module: moduleItem* EOF

- section comments are comments that start with ``///``. They're used to render text
  between production rules and split grammar definition in sections.

  Example:

  .. code-block:: antlr

     /// **Module definition**
     ///
     /// This paragraph describes the ``Module definition``
     /// section of the grammar.

     module: moduleItem* EOF

     moduleItem: import | symbol

  .. versionadded:: 1.2.0

There are also restrictions on were documentation and control comments may
appear:

- documentation comments can be placed either at the beginning of the file,
  before the ``grammar`` keyword (in which case they document the whole
  grammar), or they can be found right before a production rule or a fragment
  declaration (in which case they are rendered as a rule description).
  Also, they can be embedded into the rule description, in which case they
  are rendered as part of the railroad diagram;
- control comments can only be placed before a production rule declaration.
  They only affect rendering of that specific production rule;
- multiple documentation and control comments can appear before a rule. In this
  case, the first documentation comment will be rendered before automatically
  generated railroad diagram, all sequential documentation comments will
  be rendered after it, and all control comments will be applied before
  rendering documentation comments;
- section comments can only be placed between rules in the main section
  of a file.

.. _control_comments:

Control comments
~~~~~~~~~~~~~~~~

The list of control comments includes:

- ``//@ doc:nodoc`` -- exclude this rule from ``autogrammar`` output.

- ``//@ doc:inline`` -- exclude this rule from ``autogrammar`` output; any
  automatically generated railroad diagram that refer this rule will
  include its contents instead of a single node.

  Useful for fragments and simple lexer rules.

  For example

  .. code-block:: antlr

     NUMBER
         : '-'? ('0' | [1-9] [0-9]*) ('.' [0-9]+)? EXPONENT?
         ;

     //@ doc:inline
     fragment EXPONENT
         : ('e' | 'E')? ('+' | '-')? [0-9]+
         ;

  will produce the :a4:r:`Json.NUMBER` rule (note how exponent is rendered
  inside of the number diagram).

- ``//@ doc:no-diagram`` -- do not generate railroad diagram.

- ``//@ doc:importance <int>`` -- controls the 'importance' of a rule.

  By default, all rules have importance of ``1``.

  Rules with importance of ``0`` will be rendered off the main line in optional
  groups:

  .. parser-rule-diagram:: R1? R0?;

     //@ doc:name Rule with importance 0
     //@ doc:importance 0
     R0 : EOF;

     //@ doc:name Rule with importance 1
     //@ doc:importance 1
     R1 : EOF

  In alternative groups, rule with the highest importance will be centered:

  .. parser-rule-diagram:: (R0 | R1) (R2 | R1);

     //@ doc:name Rule with importance 0
     //@ doc:importance 0
     R0 : EOF;

     //@ doc:name Rule with importance 1
     //@ doc:importance 1
     R1 : EOF;

     //@ doc:name Rule with importance 2
     //@ doc:importance 2
     R2 : EOF

- ``//@ doc:unimportant`` -- set importance to ``0``.

- ``//@ doc:name <str>`` -- set a human-readable name for this rule.
  See :rst:opt:`a4:rule:name` option.


.. _config:

Configuration
-------------

.. _custom_style:

Customizing diagram style
~~~~~~~~~~~~~~~~~~~~~~~~~

To customize diagram style, one can replace `the default css file <https://github.com/AmatanHead/sphinx-a4doc/blob/master/sphinx_a4doc/_static/a4_railroad_diagram.css>`_
by placing a ``a4_railroad_diagram.css`` file to the ``_static`` directory.

.. . .. _custom_lookup:

.. . Customizing process of grammar files lookup
.. . ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Example output
--------------

This example was generated from
`Json.g4 <https://github.com/AmatanHead/sphinx-a4doc/blob/master/docs/examples/Json.g4>`_.

.. a4:autogrammar:: ./Json
   :only-reachable-from: value

Indices and tables
------------------

* :ref:`genindex`
* :ref:`search`
