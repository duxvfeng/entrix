"""Expression DSL for gate conditions."""
import re

from entrix.harness.evidence import Evidence

# Simple expression parser for MVP
# Supports: ==, !=, <, <=, >, >=, +, -, *, /, in, and, or, not, parentheses


class ExpressionEvaluator:
    """Evaluator for gate condition expressions."""

    def __init__(self, expression: str) -> None:
        self.expression = expression.strip()
        self.pos = 0

    def evaluate(self, evidence: Evidence) -> bool:
        """Evaluate expression against evidence.

        Args:
            evidence: Evidence object to evaluate against

        Returns:
            Boolean result of evaluation

        Raises:
            Exception: If expression evaluation fails
        """
        result = self._parse_expression(evidence)
        self._skip_whitespace()
        if self.pos != len(self.expression):
            raise SyntaxError(f"Unexpected token at position {self.pos}")
        return bool(result)

    def _parse_expression(self, evidence: Evidence):
        """Parse and evaluate expression."""
        return self._parse_or(evidence)

    def _parse_or(self, evidence: Evidence):
        """Parse OR expression."""
        left = self._parse_and(evidence)

        while self._match("or"):
            right = self._parse_and(evidence)
            left = left or right

        return left

    def _parse_and(self, evidence: Evidence):
        """Parse AND expression."""
        left = self._parse_not(evidence)

        while self._match("and"):
            right = self._parse_not(evidence)
            left = left and right

        return left

    def _parse_not(self, evidence: Evidence):
        """Parse NOT expression."""
        if self._match("not"):
            operand = self._parse_comparison(evidence)
            return not operand
        return self._parse_comparison(evidence)

    def _parse_comparison(self, evidence: Evidence):
        """Parse comparison expression."""
        left = self._parse_addition(evidence)

        # Check multi-character operators first
        if self._match(">="):
            right = self._parse_addition(evidence)
            return left >= right
        elif self._match("<="):
            right = self._parse_addition(evidence)
            return left <= right
        elif self._match("!="):
            right = self._parse_addition(evidence)
            return left != right
        elif self._match("=="):
            right = self._parse_addition(evidence)
            return left == right
        elif self._match("<"):
            right = self._parse_addition(evidence)
            return left < right
        elif self._match(">"):
            right = self._parse_addition(evidence)
            return left > right
        elif self._match("in"):
            right = self._parse_addition(evidence)
            return left in right if isinstance(right, (list, str)) else False

        return left

    def _parse_addition(self, evidence: Evidence):
        """Parse addition/subtraction."""
        left = self._parse_multiplication(evidence)

        while True:
            if self._match("+"):
                left = left + self._parse_multiplication(evidence)
            elif self._match("-"):
                left = left - self._parse_multiplication(evidence)
            else:
                break

        return left

    def _parse_multiplication(self, evidence: Evidence):
        """Parse multiplication/division."""
        left = self._parse_primary(evidence)

        while True:
            if self._match("*"):
                left = left * self._parse_primary(evidence)
            elif self._match("/"):
                left = left / self._parse_primary(evidence)
            else:
                break

        return left

    def _parse_primary(self, evidence: Evidence):
        """Parse primary expression."""
        if self._match("("):
            expr = self._parse_expression(evidence)
            self._consume(")")
            return expr

        if self._match("["):
            values: list[object] = []
            if self._match("]"):
                return values
            while True:
                values.append(self._parse_primary(evidence))
                if self._match("]"):
                    return values
                self._consume(",")

        if self._match("int"):
            self._consume("(")
            value = self._parse_expression(evidence)
            self._consume(")")
            try:
                return int(value)
            except (TypeError, ValueError) as error:
                raise ValueError("int() requires an integer-compatible value") from error

        # Parse string literals
        string_match = re.match(r'"([^"]*)"', self.expression[self.pos:])
        if string_match:
            value = string_match.group(1)
            self.pos += len(string_match.group(0))
            return value

        # Parse numbers
        number_match = re.match(r"\d+(\.\d+)?", self.expression[self.pos:])
        if number_match:
            value_str = number_match.group(0)
            self.pos += len(value_str)
            return float(value_str) if "." in value_str else int(value_str)

        # Parse field access
        return self._parse_field_access(evidence)

    def _parse_field_access(self, evidence: Evidence):
        """Parse field access expression."""
        # Simple field access like: status, summary.score, summary.nested.deep.value
        field_match = re.match(r"([a-zA-Z_][a-zA-Z0-9_.]*)", self.expression[self.pos:])
        if field_match:
            field_path = field_match.group(1)
            self.pos += len(field_path)
            return self._get_field_value(evidence, field_path)

        raise SyntaxError(f"Expected expression at position {self.pos}")

    def _get_field_value(self, evidence: Evidence, field_path: str):
        """Get value from evidence by field path."""
        parts = field_path.split(".")
        value = evidence

        for part in parts:
            if hasattr(value, part):
                value = getattr(value, part)
            elif isinstance(value, dict) and part in value:
                value = value[part]
            else:
                # Field doesn't exist - raise an error instead of returning None
                raise AttributeError(f"Field '{field_path}' not found in evidence")

        return value

    def _match(self, token: str) -> bool:
        """Check if current position matches token."""
        self._skip_whitespace()
        if not self.expression.startswith(token, self.pos):
            return False

        next_pos = self.pos + len(token)
        if token.isidentifier() and next_pos < len(self.expression):
            if self.expression[next_pos].isalnum() or self.expression[next_pos] == "_":
                return False
        self.pos = next_pos
        return True

    def _consume(self, char: str):
        """Consume specific character."""
        if not self._match(char):
            raise SyntaxError(f"Expected '{char}' at position {self.pos}")

    def _skip_whitespace(self) -> None:
        while self.pos < len(self.expression) and self.expression[self.pos].isspace():
            self.pos += 1


def evaluate_condition(condition: str, evidence: Evidence) -> bool:
    """Evaluate gate condition expression against evidence.

    Args:
        condition: Expression string to evaluate
        evidence: Evidence object

    Returns:
        Boolean result of evaluation
    """
    evaluator = ExpressionEvaluator(condition)
    return evaluator.evaluate(evidence)


class _SyntaxValue:
    """Placeholder value used to parse a condition without real evidence."""

    def __getattr__(self, _name: str) -> "_SyntaxValue":
        return self

    def __bool__(self) -> bool:
        return True

    def __int__(self) -> int:
        return 0

    def __float__(self) -> float:
        return 0.0

    def __eq__(self, _other: object) -> bool:
        return True

    def __ne__(self, _other: object) -> bool:
        return False

    def __lt__(self, _other: object) -> bool:
        return True

    def __le__(self, _other: object) -> bool:
        return True

    def __gt__(self, _other: object) -> bool:
        return True

    def __ge__(self, _other: object) -> bool:
        return True

    def __add__(self, _other: object) -> "_SyntaxValue":
        return self

    def __sub__(self, _other: object) -> "_SyntaxValue":
        return self

    def __mul__(self, _other: object) -> "_SyntaxValue":
        return self

    def __truediv__(self, _other: object) -> "_SyntaxValue":
        return self


class _SyntaxEvidence(Evidence, _SyntaxValue):
    """Evidence-shaped placeholder that accepts arbitrary field access."""

    def __init__(self) -> None:
        # Do not populate Evidence defaults: missing fields must remain symbolic.
        pass


def validate_condition_syntax(condition: str) -> None:
    """Raise when a condition cannot be parsed, without validating its fields."""
    ExpressionEvaluator(condition).evaluate(_SyntaxEvidence())
