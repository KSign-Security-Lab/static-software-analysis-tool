import re
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

from .constants import KEYWORDS


class ASTVisitor(ABC):
    """Abstract base class for AST visitors."""

    @abstractmethod
    def visit_node(
        self, node: Dict[str, Any], context: Optional[Dict[str, Any]] = None
    ) -> Any:
        """Visit a single AST node. Return True to continue traversal, False to stop."""
        pass

    def visit_children(
        self, node: Dict[str, Any], context: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Override to control child traversal. Return True to visit children, False to skip."""
        return True


class ASTTraverser:
    """Unified AST traversal system with visitor pattern support."""

    def __init__(self):
        self.visitors: List[ASTVisitor] = []

    def add_visitor(self, visitor: ASTVisitor):
        """Add a visitor to the traverser."""
        self.visitors.append(visitor)

    def traverse(self, node: Any, context: Optional[Dict[str, Any]] = None) -> Any:
        """Traverse AST starting from the given node."""
        if context is None:
            context = {}

        return self._traverse_recursive(node, context)

    def _traverse_recursive(self, node: Any, context: Dict[str, Any]) -> Any:
        """Recursive traversal implementation."""
        if not isinstance(node, dict):
            return node

        # Visit current node with all visitors
        for visitor in self.visitors:
            result = visitor.visit_node(node, context)
            if result is False:  # Stop traversal if visitor returns False
                return result

        # Visit children if any visitor allows it
        should_visit_children = True
        for visitor in self.visitors:
            if not visitor.visit_children(node, context):
                should_visit_children = False
                break

        if should_visit_children:
            children = node.get("children", []) or []
            for child in children:
                self._traverse_recursive(child, context)

        return node

    def traverse_with_stack(
        self, node: Any, context: Optional[Dict[str, Any]] = None
    ) -> Any:
        """Iterative traversal using stack (for deep trees)."""
        if context is None:
            context = {}

        stack = [node]
        while stack:
            current = stack.pop()
            if not isinstance(current, dict):
                continue

            # Visit current node
            for visitor in self.visitors:
                result = visitor.visit_node(current, context)
                if result is False:
                    return result

            # Add children to stack
            children = current.get("children", []) or []
            for child in reversed(children):  # Reverse to maintain order
                if isinstance(child, dict):
                    stack.append(child)

        return node


# =============================================================================
# Specific Visitor Implementations
# =============================================================================


class IDCollectorVisitor(ASTVisitor):
    """Visitor to collect node IDs during traversal."""

    def __init__(self):
        self.ids: Dict[int, Dict[str, Any]] = {}

    def visit_node(
        self, node: Dict[str, Any], context: Optional[Dict[str, Any]] = None
    ) -> Any:
        nid = node.get("id")
        if isinstance(nid, int):
            self.ids[nid] = node
        return True


class ParameterCollectorVisitor(ASTVisitor):
    """Visitor to collect parameter names during traversal."""

    def __init__(self):
        self.names: List[str] = []
        self.seen: Set[str] = set()

    def visit_node(
        self, node: Dict[str, Any], context: Optional[Dict[str, Any]] = None
    ) -> Any:
        if node.get("nodeType") == "ParameterDeclaration":
            nm = node.get("name")
            if isinstance(nm, str) and nm and nm not in self.seen:
                self.names.append(nm)
                self.seen.add(nm)
        return True


class IdentifierCollectorVisitor(ASTVisitor):
    """Visitor to collect identifiers with various filtering options."""

    def __init__(self, skip_sizeof: bool = True, skip_callee: bool = True):
        self.names: List[str] = []
        self.seen: Set[str] = set()
        self.skip_sizeof = skip_sizeof
        self.skip_callee = skip_callee
        self.under_sizeof = False

    def visit_node(
        self, node: Dict[str, Any], context: Optional[Dict[str, Any]] = None
    ) -> Any:
        nt = node.get("nodeType")

        # Handle sizeof expressions
        if nt == "SizeOfExpression":
            if self.skip_sizeof:
                self.under_sizeof = True
                # Visit children with sizeof flag
                children = node.get("children", []) or []
                for child in children:
                    if isinstance(child, dict):
                        old_flag = self.under_sizeof
                        self.under_sizeof = True
                        self.visit_node(child, context)
                        self.under_sizeof = old_flag
                return False  # Don't visit children normally
            return True

        # Handle call expressions
        if nt in {"StandardLibCall", "UserDefinedCall", "CallExpression"}:
            if self._is_macro_const_call(node):
                return False  # Skip macro constant calls

            # Skip callee if requested
            if self.skip_callee:
                children = node.get("children", []) or []
                if (
                    children
                    and isinstance(children[0], dict)
                    and children[0].get("nodeType") == "Identifier"
                ):
                    # Skip first child (callee)
                    for child in children[1:]:
                        if isinstance(child, dict):
                            self.visit_node(child, context)
                    return False  # Don't visit children normally
            return True

        # Handle member access
        if nt == "MemberAccess" and not self.under_sizeof:
            full_name = self._get_member_full_name(node)
            if full_name and full_name not in KEYWORDS and full_name not in self.seen:
                self.names.append(full_name)
                self.seen.add(full_name)
            return False  # Don't visit children for member access

        # Handle identifiers
        if nt == "Identifier" and not self.under_sizeof:
            nm = node.get("name")
            if (
                isinstance(nm, str)
                and nm
                and nm not in KEYWORDS
                and nm not in self.seen
            ):
                self.names.append(nm)
                self.seen.add(nm)
            return False  # Don't visit children for identifiers

        return True

    def _is_macro_const_call(self, node: Dict[str, Any]) -> bool:
        """Check if this is a macro constant call."""
        if not isinstance(node, dict) or node.get("nodeType") != "UserDefinedCall":
            return False

        # Find all ParameterList/ArgumentList nodes
        lists = []
        stack = list(node.get("children") or [])
        while stack:
            z = stack.pop()
            if not isinstance(z, dict):
                continue
            nt = z.get("nodeType")
            if nt in {"ParameterList", "ArgumentList"}:
                lists.append(z)
            for c in z.get("children") or []:
                if isinstance(c, dict):
                    stack.append(c)

        if not lists:
            return False

        # Check if any list has CompoundStatement descendants
        for pl in lists:
            if self._has_compound_statement(pl):
                return True
        return False

    def _has_compound_statement(self, node: Dict[str, Any]) -> bool:
        """Check if node has CompoundStatement descendants."""
        stack = [node]
        while stack:
            x = stack.pop()
            if not isinstance(x, dict):
                continue
            if x.get("nodeType") == "CompoundStatement":
                return True
            for cc in x.get("children") or []:
                if isinstance(cc, dict):
                    stack.append(cc)
        return False

    def _get_member_full_name(self, node: Dict[str, Any]) -> Optional[str]:
        """Get full member access name like 'base.field'."""
        if not isinstance(node, dict) or node.get("nodeType") != "MemberAccess":
            return None

        kids = node.get("children") or []
        base = kids[0] if len(kids) > 0 else None
        field = kids[1] if len(kids) > 1 else None

        base_name = self._get_identifier_name(base)
        field_name = self._get_identifier_name(field)

        if base_name and field_name:
            return f"{base_name}.{field_name}"
        return None

    def _get_identifier_name(self, node: Optional[Dict[str, Any]]) -> Optional[str]:
        """Get identifier name from node."""
        if not isinstance(node, dict):
            return None
        if node.get("nodeType") == "Identifier":
            return node.get("name")
        return None


class CallCollectorVisitor(ASTVisitor):
    """Visitor to collect call expressions during traversal."""

    def __init__(self):
        self.calls: List[Tuple[str, List[Dict[str, Any]]]] = []

    def visit_node(
        self, node: Dict[str, Any], context: Optional[Dict[str, Any]] = None
    ) -> Any:
        nt = node.get("nodeType")
        kids = node.get("children", []) or []

        if nt == "CallExpression":
            callee = kids[0] if kids else None
            fname = (
                callee.get("name") or ""
                if isinstance(callee, dict) and callee.get("nodeType") == "Identifier"
                else ""
            )
            args = kids[1:] if len(kids) > 1 else []
            self.calls.append((fname, args))
            return True  # Continue to visit arguments

        elif nt in {"StandardLibCall", "UserDefinedCall"}:
            fname = node.get("name") or ""
            # Find ParameterList or ArgumentList
            plist = next(
                (
                    c
                    for c in kids
                    if isinstance(c, dict)
                    and c.get("nodeType") in {"ParameterList", "ArgumentList"}
                ),
                None,
            )
            args = plist.get("children", []) if isinstance(plist, dict) else []
            self.calls.append((fname, args))
            return True  # Continue to visit arguments

        return True


class FirstCallFinderVisitor(ASTVisitor):
    """Visitor to find the first call node."""

    def __init__(self):
        self.first_call = None

    def visit_node(
        self, node: Dict[str, Any], context: Optional[Dict[str, Any]] = None
    ) -> Any:
        if self.first_call is not None:
            return False  # Stop traversal once found

        if node.get("nodeType") in {
            "StandardLibCall",
            "UserDefinedCall",
            "CallExpression",
        }:
            self.first_call = node
            return False  # Stop traversal

        return True


class IndexingCheckerVisitor(ASTVisitor):
    """Visitor to check for array indexing."""

    def __init__(self, skip_sizeof: bool = True):
        self.found = False
        self.skip_sizeof = skip_sizeof
        self.under_sizeof = False

    def visit_node(
        self, node: Dict[str, Any], context: Optional[Dict[str, Any]] = None
    ) -> Any:
        if self.found:
            return False  # Stop if already found

        nt = node.get("nodeType")

        # Handle sizeof expressions
        if nt == "SizeOfExpression":
            if self.skip_sizeof:
                self.under_sizeof = True
                # Visit children with sizeof flag
                children = node.get("children", []) or []
                for child in children:
                    if isinstance(child, dict):
                        old_flag = self.under_sizeof
                        self.under_sizeof = True
                        self.visit_node(child, context)
                        self.under_sizeof = old_flag
                return False  # Don't visit children normally
            return True

        # Check for array subscript
        if nt == "ArraySubscriptExpression":
            self.found = True
            return False  # Stop traversal

        # Check for pointer arithmetic pattern *(p+i)
        if nt in {"UnaryOperator", "UnaryExpression"} and node.get("operator") == "*":
            children = node.get("children", []) or []
            for ch in children:
                if (
                    isinstance(ch, dict)
                    and ch.get("nodeType") == "BinaryExpression"
                    and ch.get("operator") in {"+", "-"}
                ):
                    self.found = True
                    return False  # Stop traversal

        return True


class DFGUtils:
    @staticmethod
    def _as_int(x, d=0):
        try:
            return int(x)
        except Exception:
            return d

    @staticmethod
    def _as_float(x, d=0.0):
        try:
            return float(x)
        except Exception:
            return d

    # =============================================================================
    # AST Navigation and Indexing
    # =============================================================================

    def _index_ast_by_id(self, node: Any) -> Dict[int, Dict[str, Any]]:
        """Build a mapping from node ID to AST node."""
        visitor = IDCollectorVisitor()
        traverser = ASTTraverser()
        traverser.add_visitor(visitor)
        traverser.traverse(node)
        return visitor.ids

    def _collect_param_names(self, ast_json: Dict[str, Any]) -> List[str]:
        """Collect parameter names from AST."""
        visitor = ParameterCollectorVisitor()
        traverser = ASTTraverser()
        traverser.add_visitor(visitor)
        traverser.traverse(ast_json)

        # 순서보존 dedupe
        seen: set = set()
        out: List[str] = []
        for nm in visitor.names:
            # 빈 문자열/플레이스홀더 제외 + 중복 제거
            if nm and nm != "<empty>" and nm not in seen:
                seen.add(nm)
                out.append(nm)
        return out

    # =============================================================================
    # AST Node Type Checking
    # =============================================================================

    def _is_member_access(self, n):
        """Check if node is a member access."""
        return isinstance(n, dict) and n.get("nodeType") == "MemberAccess"

    def _get_condition_node(self, node_type: str, ast_node: dict):
        """
        제어문 AST 노드에서 '조건식' 서브트리를 돌려준다.
        - If: children[0]
        - For: children[1]   ← (init, cond, inc)
        - While: children[0]
        - Do/DoWhile: 마지막 비-CompoundStatement
        """
        if not isinstance(ast_node, dict):
            return None
        kids = ast_node.get("children") or []
        if node_type == "IfStatement":
            return kids[0] if len(kids) >= 1 and isinstance(kids[0], dict) else None
        if node_type == "ForStatement":
            return kids[1] if len(kids) >= 2 and isinstance(kids[1], dict) else None
        if node_type == "WhileStatement":
            return kids[0] if len(kids) >= 1 and isinstance(kids[0], dict) else None
        if node_type in {"DoWhileStatement", "DoStatement"}:
            for k in reversed(kids):
                if isinstance(k, dict) and k.get("nodeType") != "CompoundStatement":
                    return k
            return None
        return None

    def _callee_name_from_arglist(self, ast_json, arglist_node: dict) -> str:
        """ParameterList/ArgumentList에서 callee 이름을 AST의 name으로 가져옴.
        CallExpression.name이 없으면 첫 자식 Identifier.name 사용."""
        call = self._find_enclosing_call_for(ast_json, arglist_node)
        if not isinstance(call, dict):
            return ""
        nm = call.get("name")
        if isinstance(nm, str) and nm:
            return nm
        kids = call.get("children") or []
        if (
            kids
            and isinstance(kids[0], dict)
            and kids[0].get("nodeType") == "Identifier"
        ):
            nm2 = kids[0].get("name")
            if isinstance(nm2, str) and nm2:
                return nm2
        return ""

    def _find_enclosing_call_for(self, ast_json, node: dict) -> dict | None:
        """ParameterList/ArgumentList 노드의 상위 CallExpression을 찾아 반환."""
        if not isinstance(node, dict):
            return None
        target = node
        target_id = node.get("id") or node.get("orig_id")
        stack = [ast_json]
        while stack:
            n = stack.pop()
            if not isinstance(n, dict):
                continue
            if n.get("nodeType") in {
                "StandardLibCall",
                "UserDefinedCall",
                "CallExpression",
            }:
                for c in n.get("children") or []:
                    if not isinstance(c, dict):
                        continue
                    if c is target:
                        return n
                    cid = c.get("id") or c.get("orig_id")
                    if target_id is not None and cid is not None and cid == target_id:
                        return n
            stack.extend([c for c in (n.get("children") or []) if isinstance(c, dict)])
        return None

    # =============================================================================
    # AST Expression Processing
    # =============================================================================

    def _unwrap_cast_paren(self, n):
        """Peel Cast/Paren wrappers to reach the core expression."""
        while isinstance(n, dict) and n.get("nodeType") in {
            "CastExpression",
            "CStyleCastExpr",
            "ParenExpression",
            "ParenExpr",
        }:
            kids = n.get("children") or []
            n = kids[0] if kids else n
        return n

    def _member_parts(self, n):
        """Return (base_name, field_name, full_name='base.field') for a member access node."""
        if not self._is_member_access(n):
            return None, None, None
        kids = n.get("children") or []
        base = kids[0] if len(kids) > 0 else None
        field = kids[1] if len(kids) > 1 else None
        base_name = (
            base.get("name")
            if isinstance(base, dict) and base.get("nodeType") == "Identifier"
            else None
        )
        field_name = (
            field.get("name")
            if isinstance(field, dict) and field.get("nodeType") == "Identifier"
            else None
        )
        full = f"{base_name}.{field_name}" if base_name and field_name else None
        return base_name, field_name, full

    def _fullname_from_expr(self, n):
        """Return identifier (with field-sensitivity, e.g., 's.charFirst') from an expression.
        Handles PointerDereference/Unary '*'/'&', Cast/Paren, and ArraySubscript base.
        """
        # 0) null/primitive guard
        if n is None:
            return None

        # 1) unwrap cast/paren first
        n = self._unwrap_cast_paren(n)

        # 2) if array subscript, resolve its base first-child
        if isinstance(n, dict) and n.get("nodeType") == "ArraySubscriptExpression":
            kids = n.get("children") or []
            n = kids[0] if kids else n
            n = self._unwrap_cast_paren(n)

        # 3) peel pointer dereference or address-of to reach the underlying lvalue
        while isinstance(n, dict) and (
            n.get("nodeType") == "PointerDereference"
            or (
                n.get("nodeType") in {"UnaryOperator", "UnaryExpression"}
                and n.get("operator") in {"*", "&"}
            )
        ):
            kids = n.get("children") or []
            n = kids[0] if kids else n
            n = self._unwrap_cast_paren(n)

        # 4) member access wins (field-sensitivity)
        if self._is_member_access(n):
            return self._member_parts(n)[2]

        # 5) plain identifier
        if isinstance(n, dict) and n.get("nodeType") == "Identifier":
            return n.get("name")

        return None

    def _unwrap_ast(
        self,
        node: dict | None,
        strip_addr: bool = False,
        strip_cast: bool = True,
        strip_paren: bool = True,
    ) -> dict | None:
        """AST 표현식에서 바깥 래핑을 옵션대로 벗겨 내부 '핵심' 표현식을 반환."""
        n = node
        while isinstance(n, dict):
            nt = n.get("nodeType")

            if strip_cast and nt in {"CastExpression", "CStyleCastExpr"}:
                kids = [c for c in (n.get("children") or []) if isinstance(c, dict)]
                n = next(
                    (
                        c
                        for c in kids
                        if c.get("nodeType")
                        not in {"TypeRef", "TypeName", "TypeSpecifier"}
                    ),
                    None,
                )
                continue

            if strip_addr and (
                nt == "AddressOfExpression"
                or (nt == "UnaryOperator" and n.get("operator") in {"&", "&amp;"})
            ):
                kids = [c for c in (n.get("children") or []) if isinstance(c, dict)]
                n = kids[0] if kids else None
                continue
            break
        return n

    # =============================================================================
    # Identifier and Variable Extraction
    # =============================================================================

    def _idents_from_ast_node(
        self,
        node: Dict[str, Any] | None,
        *,
        skip_sizeof: bool = True,
        skip_callee: bool = True,
    ) -> List[str]:
        """
        식별자(이름) 추출기.
        - Identifier: 그대로 수집
        - MemberAccess: 'base.field[.subfield...]' 1토큰
        - sizeof(...) 내부 식별자는 기본 스킵
        - CallExpression의 첫 자식(callee) 기본 스킵
        - **매크로 상수(UserDefinedCall→ParameterList/ArgumentList→…→Literal)는 식별자로 취급하지 않음**
        - 순서 보존 dedupe
        """
        visitor = IdentifierCollectorVisitor(
            skip_sizeof=skip_sizeof, skip_callee=skip_callee
        )
        traverser = ASTTraverser()
        traverser.add_visitor(visitor)
        traverser.traverse(node)
        return visitor.names

    def _has_indexing(
        self, node: Dict[str, Any] | None, *, skip_sizeof: bool = True
    ) -> bool:
        """Check if expression has array indexing."""
        visitor = IndexingCheckerVisitor(skip_sizeof=skip_sizeof)
        traverser = ASTTraverser()
        traverser.add_visitor(visitor)
        traverser.traverse(node)
        return visitor.found

    def _extract_address_of_ident(self, node: Dict[str, Any] | None) -> str:
        """scanf류 인자의 &v 에서 v 추출 (단순 패턴)"""
        if not isinstance(node, dict):
            return ""
        nt = node.get("nodeType")
        if nt in {"UnaryOperator", "UnaryExpression"} and node.get("operator") == "&":
            for ch in node.get("children", []) or []:
                if isinstance(ch, dict) and ch.get("nodeType") == "Identifier":
                    nm = ch.get("name")
                    if isinstance(nm, str):
                        return nm
        # 더 깊은 경우에도 첫 식별자 반환
        ids = self._idents_from_ast_node(node, skip_sizeof=True, skip_callee=True)
        return ids[0] if ids else ""

    # =============================================================================
    # Call Processing
    # =============================================================================

    def _iter_calls_ast(self, node: Dict[str, Any]):
        """Iterate over call expressions in AST."""
        visitor = CallCollectorVisitor()
        traverser = ASTTraverser()
        traverser.add_visitor(visitor)
        traverser.traverse(node)

        for call in visitor.calls:
            yield call

    def _find_first_call_node(self, node):
        """Find the first call node in AST."""
        visitor = FirstCallFinderVisitor()
        traverser = ASTTraverser()
        traverser.add_visitor(visitor)
        traverser.traverse(node)
        return visitor.first_call

    # =============================================================================
    # Guard and Condition Processing
    # =============================================================================

    def _guards_from_condition_ast(self, cond_ast: dict) -> dict:
        """
        조건식 AST에서 변수별 가드 증거를 추출한다.
        반환 예:
        {"data": {"lower":1, "upper":1, "upper_const":0.1}}
        규칙:
        - x>=0, x>0 -> lower=1
        - x<=K, x<K (K=정수리터럴) -> upper=1, upper_const=norm_val(K)
        - AND(&&)는 양쪽 모두 병합, OR(||)는 보수적으로 '합집합' 병합
        - 좌변/우변 뒤집힘(예: 0 < x, 10 > x)도 처리
        - 식별자는 Identifier 또는 MemberAccess(base.field) 허용
        - 비상수 상계(예: x < N)는 upper=1만 줄지, upper_const는 0.0 유지(정규화 불가)
        """
        out: dict[str, dict] = {}

        # ---------- helpers ----------
        def _norm_val(k: int) -> float:
            try:
                k = int(k)
                if k <= 0:
                    return 0.0
                # 프로젝트 일관: 10 -> 0.1 로 보이니 1/k 채택
                return 1.0 / float(k)
            except Exception:
                return 0.0

        def _is_int_literal(n: dict) -> bool:
            if not isinstance(n, dict):
                return False
            if n.get("nodeType") in {"Literal", "IntegerLiteral", "NumberLiteral"}:
                t = (n.get("type") or "").lower()
                return "int" in t or t == ""  # 일부 파서에서 type 비울 수 있음
            return False

        def _int_from_node(n: dict | None) -> int | None:
            # Literal("10"), 혹은 Unary - Literal("10")
            if not isinstance(n, dict):
                return None
            if _is_int_literal(n):
                v = n.get("value")
                try:
                    return int(str(v).strip())
                except Exception:
                    # fallback: 코드에서 추출
                    code = n.get("code", "")
                    import re

                    m = re.search(r"-?\d+", code)
                    return int(m.group(0)) if m else None
            # Unary - <literal>
            if (
                n.get("nodeType") in {"UnaryOperator", "UnaryExpression"}
                and n.get("operator") == "-"
            ):
                kids = n.get("children") or []
                k0 = kids[0] if kids else None
                val = _int_from_node(k0)
                return -val if isinstance(val, int) else None
            # 괄호로 감싼 케이스 (ParenthesizedExpression 류)
            if n.get("nodeType") in {"ParenExpression", "ParenthesizedExpression"}:
                ks = n.get("children") or []
                return _int_from_node(ks[0]) if ks else None
            return None

        def _ident_name(n: dict | None) -> str | None:
            if not isinstance(n, dict):
                return None
            nt = n.get("nodeType")
            if nt == "Identifier":
                nm = n.get("name")
                return nm if isinstance(nm, str) and nm else None
            if nt == "MemberAccess":
                kids = n.get("children") or []
                base = kids[0] if len(kids) > 0 else None
                field = kids[1] if len(kids) > 1 else None
                b = _ident_name(base)
                f = _ident_name(field)
                if b and f:
                    return f"{b}.{f}"
                return b or f
            # 괄호/캐스트로 감싼 경우 풀어주기
            if nt in {
                "ParenExpression",
                "ParenthesizedExpression",
                "CStyleCastExpression",
                "CXXStaticCastExpr",
                "UnaryOperator",
                "UnaryExpression",
            }:
                kids = n.get("children") or []
                return _ident_name(kids[0]) if kids else None
            return None

        def _emit_lower(var: str):
            if not var:
                return
            e = out.setdefault(var, {"lower": 0, "upper": 0, "upper_const": 0.0})
            e["lower"] = 1

        def _emit_upper(var: str, k: int | None):
            if not var:
                return
            e = out.setdefault(var, {"lower": 0, "upper": 0, "upper_const": 0.0})
            e["upper"] = 1
            if isinstance(k, int):
                e["upper_const"] = max(e["upper_const"], _norm_val(k))  # 최대값 유지

        # ---------- recursive visit ----------
        def visit(n: dict | None):
            if not isinstance(n, dict):
                return
            nt = n.get("nodeType")
            if nt == "BinaryExpression":
                op = n.get("operator")
                ch = n.get("children") or []
                a = ch[0] if len(ch) > 0 else None
                b = ch[1] if len(ch) > 1 else None

                # 논리연산: && / ||
                if op in {"&&", "and", "AND"}:
                    visit(a)
                    visit(b)
                    return
                if op in {"||", "or", "OR"}:
                    # 보수적으로 두 쪽 모두 반영(합집합)
                    visit(a)
                    visit(b)
                    return

                # 비교연산
                if op in {"<", "<=", ">", ">="}:
                    # 케이스 1) var ? const
                    v_left = _ident_name(a)
                    k_right = _int_from_node(b)

                    # 케이스 2) const ? var  (좌우 뒤집힘)
                    k_left = _int_from_node(a)
                    v_right = _ident_name(b)

                    if v_left:
                        if op in {">", ">="}:
                            # x > 0, x >= 0 → lower
                            if (k_right is not None) and k_right == 0:
                                _emit_lower(v_left)
                        elif op in {"<", "<="}:
                            # x < K, x <= K → upper(+const)
                            _emit_upper(v_left, k_right)
                        return

                    if v_right:
                        # 뒤집힌 비교는 연산자 방향 반대로 해석
                        if op in {">", ">="}:
                            # K > x ⇒ x < K
                            _emit_upper(v_right, k_left)
                        elif op in {"<", "<="}:
                            # K < x ⇒ x > K  (K가 0일 때만 lower 인정; 일반 K는 무시)
                            if (k_left is not None) and k_left == 0:
                                _emit_lower(v_right)
                        return

                    # 둘 다 변수/상수 아니면 스킵
                    return

            # 괄호/캐스트/단항은 내부로
            if nt in {
                "ParenExpression",
                "ParenthesizedExpression",
                "CStyleCastExpression",
                "CXXStaticCastExpr",
                "UnaryOperator",
                "UnaryExpression",
            }:
                for c in n.get("children") or []:
                    visit(c)
                return

            # 논리식이 다른 노드(예: ConditionalOperator 등)면 하위 탐색
            for c in n.get("children") or []:
                visit(c)

        visit(cond_ast)

        return out

    def _guards_from_for_header(self, for_ast: dict) -> dict:
        """
        for (init; cond; inc) 에서 init/inc를 읽어 하한 가드(lower)를 보강.
        - init:  i = K (K가 정수리터럴이며 K>=0)
        - inc :  i++, ++i, i += k (k>=0)  → 단조 증가가 보장될 때만 lower=1 부여
        반환 예: {"i": {"lower":1, "upper":0, "upper_const":0.0}}
        """
        out = {}

        def _emit_lower(v):
            if not v:
                return
            e = out.setdefault(v, {"lower": 0, "upper": 0, "upper_const": 0.0})
            e["lower"] = 1

        if not isinstance(for_ast, dict) or for_ast.get("nodeType") != "ForStatement":
            return out

        kids = for_ast.get("children") or []
        init = kids[0] if len(kids) >= 1 else None
        inc = kids[2] if len(kids) >= 3 else None

        # helper: 정수리터럴 추출
        def _int_from(n):
            if not isinstance(n, dict):
                return None
            if n.get("nodeType") in {"Literal", "IntegerLiteral", "NumberLiteral"}:
                try:
                    return int(str(n.get("value")).strip())
                except:
                    return None
            if (
                n.get("nodeType") in {"UnaryOperator", "UnaryExpression"}
                and n.get("operator") == "-"
            ):
                ks = n.get("children") or []
                v = _int_from(ks[0]) if ks else None
                return -v if isinstance(v, int) else None
            if n.get("nodeType") in {"ParenExpression", "ParenthesizedExpression"}:
                ks = n.get("children") or []
                return _int_from(ks[0]) if ks else None
            return None

        # helper: 식별자 이름 추출 (Identifier/MemberAccess)
        def _ident(n):
            if not isinstance(n, dict):
                return None
            nt = n.get("nodeType")
            if nt == "Identifier":
                nm = n.get("name")
                return nm if isinstance(nm, str) and nm else None
            if nt == "MemberAccess":
                ks = n.get("children") or []
                b = _ident(ks[0] if len(ks) > 0 else None)
                f = _ident(ks[1] if len(ks) > 1 else None)
                return f"{b}.{f}" if b and f else (b or f)
            if nt in {
                "ParenExpression",
                "ParenthesizedExpression",
                "CStyleCastExpression",
                "CXXStaticCastExpr",
                "UnaryOperator",
                "UnaryExpression",
            }:
                ks = n.get("children") or []
                return _ident(ks[0]) if ks else None
            return None

        # 1) init: i = K (K>=0)
        init_var = None
        init_nonneg = False
        if (
            isinstance(init, dict)
            and init.get("nodeType") == "AssignmentExpression"
            and init.get("operator") == "="
        ):
            ch = init.get("children") or []
            lhs, rhs = (ch[0] if len(ch) > 0 else None), (
                ch[1] if len(ch) > 1 else None
            )
            init_var = _ident(lhs)
            kv = _int_from(rhs)
            init_nonneg = isinstance(kv, int) and kv >= 0

        # 2) inc: ++i / i++ / i += k (k>=0)
        inc_var = None
        inc_nondecreasing = False
        if isinstance(inc, dict):
            nt = inc.get("nodeType")
            if nt in {"UnaryOperator", "UnaryExpression"} and inc.get("operator") in {
                "++"
            }:
                ks = inc.get("children") or []
                inc_var = _ident(ks[0]) if ks else None
                inc_nondecreasing = True
            elif nt == "AssignmentExpression" and inc.get("operator") in {"+="}:
                ch = inc.get("children") or []
                lhs, rhs = (ch[0] if len(ch) > 0 else None), (
                    ch[1] if len(ch) > 1 else None
                )
                inc_var = _ident(lhs)
                step = _int_from(rhs)
                inc_nondecreasing = isinstance(step, int) and step >= 0

        # 3) 결론: init와 inc가 같은 변수이고 init_nonneg & inc_nondecreasing면 lower=1
        if (
            init_var
            and inc_var
            and init_var == inc_var
            and init_nonneg
            and inc_nondecreasing
        ):
            _emit_lower(init_var)

        return out

    # =============================================================================
    # General Utility Methods (moved from DFGExtractor)
    # =============================================================================

    @staticmethod
    def _pick_dst_size_args(base: str, arg_nodes: List[Dict[str, Any]]):
        """Pick destination and size arguments based on function name."""
        dst = None
        size = None
        if base == "fgets":
            dst = arg_nodes[0] if len(arg_nodes) > 0 else None
            size = arg_nodes[1] if len(arg_nodes) > 1 else None
        elif base == "gets":
            dst = arg_nodes[0] if len(arg_nodes) > 0 else None
        elif base in {"memcpy", "memmove", "strncpy"}:
            dst = arg_nodes[0] if len(arg_nodes) > 0 else None
            size = arg_nodes[2] if len(arg_nodes) > 2 else None
        elif base in {"snprintf", "vsnprintf"}:
            dst = arg_nodes[0] if len(arg_nodes) > 0 else None
            size = arg_nodes[1] if len(arg_nodes) > 1 else None
        elif base in {"strcpy", "strcat", "sprintf", "vsprintf"}:
            dst = arg_nodes[0] if len(arg_nodes) > 0 else None
        elif base in {"read", "recv"}:
            dst = arg_nodes[1] if len(arg_nodes) > 1 else None
            size = arg_nodes[2] if len(arg_nodes) > 2 else None
        elif base == "getline":
            dst = arg_nodes[0] if len(arg_nodes) > 0 else None  # lineptr
            size = arg_nodes[1] if len(arg_nodes) > 1 else None  # n(pointer)
        elif base in {"memset"}:
            dst = arg_nodes[0] if len(arg_nodes) > 0 else None
            size = arg_nodes[2] if len(arg_nodes) > 2 else None
        elif base == "connect":
            # connect(int sockfd, const struct sockaddr *addr, socklen_t addrlen)
            dst = None  # 목적지 버퍼 개념 없음
            size = arg_nodes[2] if len(arg_nodes) > 2 else None
        return dst, size

    @staticmethod
    def _pick_kind(*gds):
        """Pick guard kind with priority: var > * > __agg__."""
        for gd in gds:
            try:
                k = int(gd.get("kind", 0))
            except Exception:
                k = 0
            if k:
                return k
        return 0

    def _decl_len(self, var: str, ast_json: Dict[str, Any]) -> str | None:
        """Get declaration length for a variable."""

        class ArrayDeclarationFinderVisitor(ASTVisitor):
            def __init__(self, target_var: str):
                self.target_var = target_var
                self.result = None

            def visit_node(
                self, node: Dict[str, Any], context: Optional[Dict[str, Any]] = None
            ) -> Any:
                if self.result is not None:
                    return False  # Stop if already found

                if (
                    isinstance(node, dict)
                    and node.get("nodeType") == "ArrayDeclaration"
                    and node.get("name") == self.target_var
                ):

                    # Try to get length from 'length' field
                    length = node.get("length")
                    if isinstance(length, str) and length:
                        self.result = length
                        return False

                    # Try to extract from code using regex
                    code = node.get("code", "") or ""
                    import re as _re

                    m = _re.search(r"\[\s*(.*?)\s*\]", code)
                    if m:
                        self.result = m.group(1)
                        return False

                return True  # Continue traversal

        visitor = ArrayDeclarationFinderVisitor(var)
        traverser = ASTTraverser()
        traverser.add_visitor(visitor)
        traverser.traverse(ast_json)
        return visitor.result

    @staticmethod
    def _norm(s: str) -> str:
        """Normalize string by removing whitespace and unnecessary parentheses."""
        s2 = re.sub(r"\s+", "", s or "")
        while s2.startswith("(") and s2.endswith(")"):
            depth = 0
            ok = True
            for i, ch in enumerate(s2):
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                    if depth == 0 and i != len(s2) - 1:
                        ok = False
                        break
            if ok:
                s2 = s2[1:-1]
            else:
                break
        return s2
