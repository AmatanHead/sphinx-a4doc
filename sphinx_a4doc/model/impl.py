import os
import re
import textwrap

from typing import *

from antlr4 import CommonTokenStream, InputStream
from antlr4.error.ErrorListener import ErrorListener

from sphinx_a4doc.model.model import ModelCache, Model, Position, RuleBase, LexerRule, ParserRule
from sphinx_a4doc.syntax import Lexer, Parser, ParserVisitor

import sphinx.util.logging

__all__ = [
    'ModelCacheImpl',
    'ModelImpl',
    'MetaLoader',
    'RuleLoader',
    'LexerRuleLoader',
    'ParserRuleLoader',
]


logger = sphinx.util.logging.getLogger(__name__)


CMD_RE = re.compile(r'''
    //@\s*doc\s*:\s*(?P<cmd>[a-zA-Z0-9_-]+)\s*(?P<ctx>.*)
    ''', re.UNICODE | re.VERBOSE)


class LoggingErrorListener(ErrorListener):
    def __init__(self, path: str, offset: int):
        self._path = path
        self._offset = offset

    def syntaxError(self, recognizer, offending_symbol, line, column, msg, e):
        logger.error(f'{self._path}:{line + self._offset}: WARNING: {msg}')


class ModelCacheImpl(ModelCache):
    def __init__(self):
        self._loaded: Dict[str, Model] = {}

    def from_file(self, path: Union[str, Tuple[str, int]]) -> 'Model':
        if isinstance(path, tuple):
            path, offset = path
        else:
            path, offset = path, 0

        path = os.path.abspath(os.path.normpath(path))

        if path in self._loaded:
            return self._loaded[path]

        if not os.path.exists(path):
            logger.error(f'unable to load {path!r}: file not found')
            model = self._loaded[path] = ModelImpl(path, offset, False)
            return model

        with open(path, 'r', encoding='utf-8', errors='strict') as f:
            self._loaded[path] = self._do_load(f.read(), path, offset, False)

        return self._loaded[path]

    def from_text(self, text: str, path: Union[str, Tuple[str, int]] = '<in-memory>') -> 'Model':
        if isinstance(path, tuple):
            path, offset = path
        else:
            path, offset = path, 0
        return self._do_load(text, path, offset, True)

    def _do_load(self, text: str, path: str, offset: int, in_memory: bool) -> 'Model':
        content = InputStream(text)

        lexer = Lexer(content)
        lexer.removeErrorListeners()
        lexer.addErrorListener(LoggingErrorListener(path, offset))

        tokens = CommonTokenStream(lexer)

        parser = Parser(tokens)
        parser.removeErrorListeners()
        parser.addErrorListener(LoggingErrorListener(path, offset))

        tree = parser.grammarSpec()

        model = ModelImpl(path, offset, in_memory)

        if parser.getNumberOfSyntaxErrors():
            return model

        MetaLoader(model, self).visit(tree)
        LexerRuleLoader(model).visit(tree)
        ParserRuleLoader(model).visit(tree)

        return model


class ModelImpl(Model):
    def __init__(self, path: str, offset: int, in_memory: bool):
        self._path = path
        self._in_memory = in_memory
        self._offset = offset

        self._lexer_rules: Dict[str, LexerRule] = {}
        self._parser_rules: Dict[str, ParserRule] = {}
        self._imports: Set[Model] = set()

    def is_in_memory(self):
        return self._in_memory

    def get_path(self) -> str:
        return self._path

    def get_offset(self) -> int:
        return self._offset

    def add_import(self, model: 'Model'):
        # actually, loader will not call this function on in-memory models
        assert not self.is_in_memory()
        assert not model.is_in_memory()
        self._imports.add(model)

    def set_lexer_rule(self, name: str, rule: LexerRule):
        self._lexer_rules[name] = rule

    def set_parser_rule(self, name: str, rule: ParserRule):
        self._parser_rules[name] = rule

    def lookup_local(self, name: str) -> Optional[RuleBase]:
        if name in self._lexer_rules:
            return self._lexer_rules[name]
        if name in self._parser_rules:
            return self._parser_rules[name]

        return None

    def get_imports(self) -> Iterable[Model]:
        return iter(self._imports)

    def get_terminals(self) -> Iterable[LexerRule]:
        return iter(set(self._lexer_rules.values()))

    def get_non_terminals(self) -> Iterable[ParserRule]:
        return iter(set(self._parser_rules.values()))


class MetaLoader(ParserVisitor):
    def __init__(self, model: ModelImpl, cache: ModelCacheImpl):
        self._model = model
        self._cache = cache
        if self._model.is_in_memory():
            self._basedir = None
        else:
            self._basedir = os.path.dirname(self._model.get_path())

    def add_import(self, name: str, position: Position):
        if self._model.is_in_memory():
            logger.error('imports are not allowed for in-memory grammars')
        else:
            model = self._cache.from_file(os.path.join(self._basedir, name + '.g4'))
            self._model.add_import(model)

    def visitParserRuleSpec(self, ctx: Parser.ParserRuleSpecContext):
        return None  # do not recurse into this

    def visitLexerRuleSpec(self, ctx: Parser.LexerRuleSpecContext):
        return None  # do not recurse into this

    def visitModeSpec(self, ctx: Parser.ModeSpecContext):
        return None  # do not recurse into this

    def visitOption(self, ctx: Parser.OptionContext):
        if ctx.name.getText() == 'tokenVocab':
            self.add_import(ctx.value.getText(),
                            Position(self._model.get_path(), ctx.start.line + self._model.get_offset()))

    def visitDelegateGrammar(self, ctx: Parser.DelegateGrammarContext):
        self.add_import(ctx.value.getText(),
                        Position(self._model.get_path(), ctx.start.line + self._model.get_offset()))

    def visitTokensSpec(self, ctx: Parser.TokensSpecContext):
        tokens: List[Parser.IdentifierContext] = ctx.defs.defs
        for token in tokens:
            rule = LexerRule(
                name=token.getText(),
                display_name=None,
                position=Position(self._model.get_path(), token.start.line + self._model.get_offset()),
                model=self._model,
                is_literal=False,
                is_fragment=False,
                content=None,
                is_doxygen_nodoc=True,
                is_doxygen_inline=True,
                is_doxygen_important=True,
                documentation=''
            )

            self._model.set_lexer_rule(rule.name, rule)


class RuleLoader(ParserVisitor):
    rule_class: Union[Type[RuleBase], Type[LexerRule], Type[ParserRule]] = None

    def __init__(self, model: ModelImpl):
        self._model = model

    def wrap_suffix(self, element, suffix):
        if element == self.rule_class.EMPTY:
            return element
        if suffix is None:
            return element
        suffix: str = suffix.getText()
        if suffix.startswith('?'):
            if isinstance(element, self.rule_class.Maybe):
                return element
            else:
                return self.rule_class.Maybe(child=element)
        if suffix.startswith('+'):
            return self.rule_class.OnePlus(child=element)
        if suffix.startswith('*'):
            return self.rule_class.ZeroPlus(child=element)
        return element

    def make_alt_rule(self, content):
        has_empty_alt = False
        alts = []

        for alt in [self.visit(alt) for alt in content]:
            if isinstance(alt, self.rule_class.Maybe):
                has_empty_alt = True
                alt = alt.child
            if alt == self.rule_class.EMPTY:
                has_empty_alt = True
            elif isinstance(alt, self.rule_class.Alternative):
                alts.extend(alt.children)
            else:
                alts.append(alt)

        if len(alts) == 0:
            return self.rule_class.EMPTY
        elif len(alts) == 1 and has_empty_alt:
            return self.rule_class.Maybe(child=alts[0])
        elif len(alts) == 1:
            return alts[0]

        rule = self.rule_class.Alternative(children=tuple(alts))

        if has_empty_alt:
            rule = self.rule_class.Maybe(rule)

        return rule

    def make_seq_rule(self, content):
        elements = []

        for element in [self.visit(element) for element in content]:
            if isinstance(element, self.rule_class.Sequence):
                elements.extend(element.children)
            else:
                elements.append(element)

        if len(elements) == 1:
            return elements[0]

        return self.rule_class.Sequence(tuple(elements))

    def load_docs(self, tokens):
        is_doxygen_nodoc = False
        is_doxygen_inline = False
        css_class = ''
        importance = 1
        name = None
        documentation_lines = []

        for token in tokens:
            text: str = token.text
            position = Position(self._model.get_path(), token.line + self._model.get_offset())
            if text.startswith('//@'):
                match = CMD_RE.match(text)

                if match is None:
                    logger.error(f'{position}: WARNING: invalid command {text!r}')
                    continue

                cmd = match['cmd']

                if cmd == 'nodoc':
                    is_doxygen_nodoc = True
                elif cmd == 'inline':
                    is_doxygen_inline = True
                elif cmd == 'unimportant':
                    importance = 0
                elif cmd == 'class':
                    css_class = match['ctx'].strip()
                elif cmd == 'importance':
                    try:
                        val = int(match['ctx'].strip())
                    except ValueError:
                        logger.error(f'{position}: WARNING: importance requires an integer argument')
                        continue
                    if val < 0:
                        logger.error(f'{position}: WARNING: importance should not be negative')
                    importance = val
                elif cmd == 'name':
                    name = match['ctx'].strip()
                    if not name:
                        logger.error(f'{position}: WARNING: name command requires an argument')
                        continue
                else:
                    logger.error(f'{position}: WARNING: unknown command {cmd!r}')

                if cmd not in ['name', 'class', 'importance'] and match['ctx']:
                    logger.warning(f'argument for {cmd!r} command is ignored')
            else:
                lines = list(map(str.strip, text.splitlines()))

                if len(lines) == 1:
                    documentation_lines.append(lines[0][3:-2].strip())
                else:
                    first_line, *lines = lines

                    first_line = first_line[3:].lstrip()
                    if first_line:
                        documentation_lines.append(first_line)

                    lines[-1] = lines[-1][:-2].rstrip()

                    if not lines[-1]:
                        lines.pop()

                    if all(line.startswith('*') for line in lines):
                        lines = [line[1:] for line in lines]

                    text = textwrap.dedent('\n'.join(lines))

                    documentation_lines.append(text)

        return dict(
            css_class=css_class,
            importance=importance,
            is_doxygen_inline=is_doxygen_inline,
            is_doxygen_nodoc=is_doxygen_nodoc,
            name=name,
            documentation='\n'.join(documentation_lines)
        )


class LexerRuleLoader(RuleLoader):
    rule_class = LexerRule

    def visitParserRuleSpec(self, ctx: Parser.ParserRuleSpecContext):
        return None  # do not recurse into this

    def visitPrequelConstruct(self, ctx: Parser.PrequelConstructContext):
        return None  # do not recurse into this

    def visitLexerRuleSpec(self, ctx: Parser.LexerRuleSpecContext):
        content: LexerRule.RuleContent = self.visit(ctx.lexerRuleBlock())

        doc_info = self.load_docs(ctx.docs)

        if isinstance(content, LexerRule.Literal):
            is_literal = True
            literal = content.content
        else:
            is_literal = False
            literal = ''

        rule = LexerRule(
            name=ctx.name.text,
            display_name=doc_info['name'] or None,
            model=self._model,
            position=Position(self._model.get_path(), ctx.start.line + self._model.get_offset()),
            content=content,
            is_doxygen_nodoc=doc_info['is_doxygen_nodoc'],
            is_doxygen_inline=doc_info['is_doxygen_inline'],
            importance=doc_info['importance'],
            css_class=doc_info['css_class'],
            documentation=doc_info['documentation'],
            is_fragment=bool(ctx.frag),
            is_literal=is_literal
        )

        self._model.set_lexer_rule(rule.name, rule)
        if is_literal:
            self._model.set_lexer_rule(literal, rule)

    def visitLexerAltList(self, ctx: Parser.LexerAltListContext):
        return self.make_alt_rule(ctx.alts)

    def visitLexerAlt(self, ctx: Parser.LexerAltContext):
        return self.visit(ctx.lexerElements())

    def visitLexerElements(self, ctx: Parser.LexerElementsContext):
        return self.make_seq_rule(ctx.elements)

    def visitLexerElementLabeled(self, ctx: Parser.LexerElementLabeledContext):
        return self.wrap_suffix(self.visit(ctx.value), ctx.suffix)

    def visitLexerElementAtom(self, ctx: Parser.LexerElementAtomContext):
        return self.wrap_suffix(self.visit(ctx.value), ctx.suffix)

    def visitLexerElementBlock(self, ctx: Parser.LexerElementBlockContext):
        return self.wrap_suffix(self.visit(ctx.value), ctx.suffix)

    def visitLexerElementAction(self, ctx: Parser.LexerElementActionContext):
        return LexerRule.EMPTY

    def visitLabeledLexerElement(self, ctx: Parser.LabeledLexerElementContext):
        return self.visit(ctx.lexerAtom() or ctx.lexerBlock())

    def visitLexerBlock(self, ctx: Parser.LexerBlockContext):
        return self.visit(ctx.lexerAltList())

    def visitCharacterRange(self, ctx: Parser.CharacterRangeContext):
        return LexerRule.Range(start=ctx.start.text, end=ctx.end.text)

    def visitTerminalRef(self, ctx: Parser.TerminalRefContext):
        return LexerRule.Reference(model=self._model, name=ctx.value.text)

    def visitTerminalLit(self, ctx: Parser.TerminalLitContext):
        content = ctx.value.text
        if content == "''":
            return LexerRule.EMPTY
        else:
            return LexerRule.Literal(content=ctx.value.text)

    def visitLexerAtomCharSet(self, ctx: Parser.LexerAtomCharSetContext):
        content = ctx.value.text
        if content == '[]':
            return LexerRule.EMPTY
        else:
            return LexerRule.CharSet(content=content)

    def visitLexerAtomWildcard(self, ctx: Parser.LexerAtomWildcardContext):
        return LexerRule.WILDCARD

    def visitNotElement(self, ctx: Parser.NotElementContext):
        return LexerRule.Negation(child=self.visit(ctx.value))

    def visitNotBlock(self, ctx: Parser.NotBlockContext):
        return LexerRule.Negation(child=self.visit(ctx.value))

    def visitBlockSet(self, ctx: Parser.BlockSetContext):
        return self.make_alt_rule(ctx.elements)

    def visitSetElementRef(self, ctx: Parser.SetElementRefContext):
        return LexerRule.Reference(model=self._model, name=ctx.value.text)

    def visitSetElementLit(self, ctx: Parser.SetElementLitContext):
        content = ctx.value.text
        if content == "''":
            return LexerRule.EMPTY
        else:
            return LexerRule.Literal(content=ctx.value.text)

    def visitSetElementCharSet(self, ctx: Parser.SetElementCharSetContext):
        content = ctx.value.text
        if content == '[]':
            return LexerRule.EMPTY
        else:
            return LexerRule.CharSet(content=content)


class ParserRuleLoader(RuleLoader):
    rule_class = ParserRule

    def visitParserRuleSpec(self, ctx: Parser.ParserRuleSpecContext):
        content: ParserRule.RuleContent = self.visit(ctx.ruleBlock())
        doc_info = self.load_docs(ctx.docs)
        rule = ParserRule(
            name=ctx.name.text,
            display_name=doc_info['name'] or None,
            model=self._model,
            position=Position(self._model.get_path(), ctx.start.line + self._model.get_offset()),
            content=content,
            is_doxygen_nodoc=doc_info['is_doxygen_nodoc'],
            is_doxygen_inline=doc_info['is_doxygen_inline'],
            importance=doc_info['importance'],
            css_class=doc_info['css_class'],
            documentation=doc_info['documentation']
        )

        self._model.set_parser_rule(rule.name, rule)

    def visitPrequelConstruct(self, ctx: Parser.PrequelConstructContext):
        return None  # do not recurse into this

    def visitLexerRuleSpec(self, ctx: Parser.LexerRuleSpecContext):
        return None  # do not recurse into this

    def visitModeSpec(self, ctx: Parser.ModeSpecContext):
        return None  # do not recurse into this

    def visitRuleAltList(self, ctx: Parser.RuleAltListContext):
        return self.make_alt_rule(ctx.alts)

    def visitAltList(self, ctx: Parser.AltListContext):
        return self.make_alt_rule(ctx.alts)

    def visitLabeledAlt(self, ctx: Parser.LabeledAltContext):
        return self.visit(ctx.alternative())

    def visitAlternative(self, ctx: Parser.AlternativeContext):
        return self.make_seq_rule(ctx.elements)

    def visitParserElementLabeled(self, ctx: Parser.ParserElementLabeledContext):
        return self.wrap_suffix(self.visit(ctx.value), ctx.suffix)

    def visitParserElementAtom(self, ctx: Parser.ParserElementAtomContext):
        return self.wrap_suffix(self.visit(ctx.value), ctx.suffix)

    def visitParserElementBlock(self, ctx: Parser.ParserElementBlockContext):
        return self.wrap_suffix(self.visit(ctx.value), ctx.suffix)

    def visitParserElementAction(self, ctx: Parser.ParserElementActionContext):
        return ParserRule.EMPTY

    def visitLabeledElement(self, ctx: Parser.LabeledElementContext):
        return self.visit(ctx.atom() or ctx.block())

    def visitBlock(self, ctx: Parser.BlockContext):
        return self.visit(ctx.altList())

    def visitAtomWildcard(self, ctx: Parser.AtomWildcardContext):
        return ParserRule.WILDCARD

    def visitTerminalRef(self, ctx: Parser.TerminalRefContext):
        return ParserRule.Reference(model=self._model, name=ctx.value.text)

    def visitTerminalLit(self, ctx: Parser.TerminalLitContext):
        return ParserRule.Reference(model=self._model, name=ctx.value.text)

    def visitRuleref(self, ctx: Parser.RulerefContext):
        return ParserRule.Reference(model=self._model, name=ctx.value.text)

    def visitNotElement(self, ctx: Parser.NotElementContext):
        return ParserRule.Negation(child=self.visit(ctx.value))

    def visitNotBlock(self, ctx: Parser.NotBlockContext):
        return ParserRule.Negation(child=self.visit(ctx.value))

    def visitBlockSet(self, ctx: Parser.BlockSetContext):
        return self.make_alt_rule(ctx.elements)

    def visitSetElementRef(self, ctx: Parser.SetElementRefContext):
        return ParserRule.Reference(model=self._model, name=ctx.value.text)

    def visitSetElementLit(self, ctx: Parser.SetElementLitContext):
        return ParserRule.Reference(model=self._model, name=ctx.value.text)

    def visitSetElementCharSet(self, ctx: Parser.SetElementCharSetContext):
        # Char sets are not allowed in parser rules,
        # yet our grammar can match them...
        return ParserRule.EMPTY

    def visitCharacterRange(self, ctx: Parser.CharacterRangeContext):
        # This also makes no sense...
        return ParserRule.EMPTY