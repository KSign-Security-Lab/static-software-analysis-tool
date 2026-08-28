
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

KEYWORDS = {"if","for","while","switch","case","return","int","char","void","NULL","sizeof","stdin","else"}
FUNCTION_META = {"FunctionEntry","FunctionDeclaration","FunctionDefinition"}
CONTROL_NODES = {"IfStatement","ForStatement","WhileStatement","SwitchStatement","DoWhileStatement","DoStatement"}

FLOW_ID = {"value":1, "index":2, "size":3, "base":4}

# ------------------------------
# DFG Extractor V1.9
# ------------------------------
class DFGExtractor:
    def __init__(self, ast_json: Dict[str,Any], ast_result: Dict[str,Any], sink_mode: str = "k1"):
        self.ast_json = ast_json
        self.ast_result = ast_result or {}

        self.ast_nodes = ast_result.get("nodes", [])
        self.ast_guard = ast_result.get("edges_ast_guard", [])
        self.pointer_vars: Set[str] = self._collect_pointer_names(self.ast_json)  # Collect PointerDeclaration



        # map: sid -> flat AST row (to fetch orig_id etc.)
        self.sid2flat: Dict[int, Dict[str, Any]] = {}
        for _row in self.ast_nodes:
            try:
                _sid = int(_row.get("sid"))
            except Exception:
                continue
            self.sid2flat[_sid] = _row
        self.sink_mode = sink_mode

        # Original AST index (id -> node)
        self.id2orig: Dict[int,Dict[str,Any]] = self._index_ast_by_id(self.ast_json)

        # Parameter list
        self.param_names: List[str] = self._collect_param_names(self.ast_json)

       
        # Result container
        self.nodes: List[Dict[str,Any]] = []   # DFG nodes (features)
        self.edges_defuse: List[Tuple[int,int,Dict[str,Any]]] = []  # <- flat Def->Use (for collection)

        # Initialize DFG nodes (share sid). Debug fields are synchronized in run()
        for n in self.ast_nodes:
            sid = int(n.get("sid"))
            code = (n.get("code") or "")
            node_type = (n.get("node_type") or "")                

            self.nodes.append({
                "sid": sid,
                "code": code,
                "node_type_id": node_type,
                # These fields will be overwritten in run() with actual DEF/USE/degree
            })

        # Final output edges (split into 'feat'/'debug') are assembled in run() into self.edges
        self.edges: List[Tuple[int,int,Dict[str,Any]]] = []

        # Cache (sid -> feat) for guard injection based on dst SID
        self._sid2feat: Dict[int, Dict[str, Any]] = {
            int(r.get("sid")): (r.get("feat") or {}) for r in self.ast_nodes if "sid" in r
        }

    # ------------------------------
    # Public: build edges + finalize node features
    # ------------------------------
    def run(self) -> Dict[str,Any]:
        import re
        from collections import defaultdict

        # Build guard information (lower/upper bounds evidence per variable)
        guard_map = self._build_guard_map()
        # Store in instance for reference during edge creation
        self.guard_map = guard_map


        # Last DEF position, duplicate edge prevention keys
        last_def: Dict[str,int] = {}
        seen_edges: Set[Tuple[int,int,str,int]] = set()  # (src,dst,var,flow_id)

        # Debug/feature synchronization buckets
        use_vars_by_sid: Dict[int, Set[str]] = defaultdict(set)
        def_vars_by_sid: Dict[int, Set[str]] = defaultdict(set)
        iba_by_sid: Dict[int, int] = defaultdict(int)           # is_buffer_access
        sink_assign_by_sid: Dict[int, int] = defaultdict(int)   # is_sink_assign

        # 노드별 특징/디버그 컨테이너
        node_feat: Dict[int, Dict[str,Any]] = {}
        node_debug: Dict[int, Dict[str,Any]] = {}

        # Call-based sink classification sets
        UNBOUNDED = {"gets","strcpy","strcat","sprintf","vsprintf"}
        BOUNDED   = {"memcpy","memmove","strncpy","snprintf","vsnprintf",
                    "fgets","read","recv","getline"}

        # Parameter -> entry DEF processing
        for p in self.param_names:
            if p and p != "<empty>":
                last_def[p] = 0
                def_vars_by_sid[0].add(p)

        # self.edges_defuse: Maintain RAW storage used in original code
        # (Convert to feat/debug upon final return)
        self.edges_defuse = []

        def ensure_feat(sid: int, node_type_id: str):
            if sid not in node_feat:
                node_feat[sid] = {
                    "node_type_id": node_type_id,
                    "in_degree_dfg": 0,
                    "out_degree_dfg": 0,
                    # counts
                    "def_count": 0,
                    "use_count": 0,
                    # buffer/sink
                    "is_buffer_access": 0,
                    "is_sink_assign": 0,
                    "is_sink_call_unbounded": 0,
                    "is_sink_call_bounded": 0,
                    "call_dst_indexed": 0,
                    "call_len_linked_to_dst": 0,
                    "call_size_nonconst": 0,
                    "call_danger_unbounded": 0,
                }
            if sid not in node_debug:
                node_debug[sid] = {"code": "", "def_vars": [], "use_vars": []}

        def _pick_dst_size_args(base: str, arg_nodes: List[Dict[str,Any]]):
            dst = None; size = None
            if base == "fgets":
                dst = arg_nodes[0] if len(arg_nodes)>0 else None
                size = arg_nodes[1] if len(arg_nodes)>1 else None
            elif base == "gets":
                dst = arg_nodes[0] if len(arg_nodes)>0 else None
            elif base in {"memcpy","memmove","strncpy"}:
                dst = arg_nodes[0] if len(arg_nodes)>0 else None
                size = arg_nodes[2] if len(arg_nodes)>2 else None
            elif base in {"snprintf","vsnprintf"}:
                dst = arg_nodes[0] if len(arg_nodes)>0 else None
                size = arg_nodes[1] if len(arg_nodes)>1 else None
            elif base in {"strcpy","strcat","sprintf","vsprintf"}:
                dst = arg_nodes[0] if len(arg_nodes)>0 else None
            elif base in {"read","recv"}:
                dst = arg_nodes[1] if len(arg_nodes)>1 else None
                size = arg_nodes[2] if len(arg_nodes)>2 else None
            elif base == "getline":
                dst = arg_nodes[0] if len(arg_nodes)>0 else None  # lineptr
                size = arg_nodes[1] if len(arg_nodes)>1 else None # n(pointer)
            elif base in {"memset"}:
                dst = arg_nodes[0] if len(arg_nodes)>0 else None
                size = arg_nodes[2] if len(arg_nodes)>2 else None
            elif base == "connect":
                # connect(int sockfd, const struct sockaddr *addr, socklen_t addrlen)
                dst = None       # 목적지 버퍼 개념 없음
                size = arg_nodes[2] if len(arg_nodes)>2 else None
            return dst, size

        


        def _add_use_edge(var: str, role: str, dst_sid: int):
            """
            Record USE and create Def->Use edges.
            - 'base' role is excluded from use_vars counts (expressed as graph edges only)
            - Guard injection merges variable-specific -> '*' -> '__agg__':
                lower/upper use OR, upper_const uses max,
                kind selects the first non-zero in priority: var > * > __agg__
            - Edges are stored as flat dicts and wrapped in feat/debug at the end
            """
            if not var or var in KEYWORDS:
                return

            # USE for debug/count: exclude base
            if role != "base":
                use_vars_by_sid[dst_sid].add(var)

            # Def->Use edges are created only when a last DEF exists
            if var not in last_def:
                return
            src = last_def[var]

            # Determine flow_id (value=1, index=2, size=3, base=4)
            fid = FLOW_ID.get(role or "value", FLOW_ID["value"])

            key = (src, dst_sid, var, fid)
            if key in seen_edges:
                return
            seen_edges.add(key)

            # ---- Guard merging (var / * / __agg__) ----
            gdst = getattr(self, "guard_map", {}).get(dst_sid, {}) or {}
            g_var = gdst.get(var) or {}
            g_all = gdst.get("*") or {}
            g_agg = gdst.get("__agg__") or {}

            # kind: var > * > __agg__ priority
            def _pick_kind(*gds):
                for gd in gds:
                    try:
                        k = int(gd.get("kind", 0))
                    except Exception:
                        k = 0
                    if k:
                        return k
                return 0

            kind = _pick_kind(g_var, g_all, g_agg)

            def _as_int(x, d=0): 
                try: return int(x)
                except Exception: return d
            def _as_float(x, d=0.0):
                try: return float(x)
                except Exception: return d

            has_lower = _as_int(g_var.get("lower", 0)) | _as_int(g_all.get("lower", 0)) | _as_int(g_agg.get("lower", 0))
            has_upper = _as_int(g_var.get("upper", 0)) | _as_int(g_all.get("upper", 0)) | _as_int(g_agg.get("upper", 0))
            upper_norm = max(
                _as_float(g_var.get("upper_const", 0.0)),
                _as_float(g_all.get("upper_const", 0.0)),
                _as_float(g_agg.get("upper_const", 0.0)),
            )


            if getattr(self, "DEBUG_GUARD", False) and dst_sid in (40,):
                print(f"[DBG][edge] {src}->{dst_sid} var={var} role={role} fid={fid} "
                        f"guard=({kind},{has_lower},{has_upper},{upper_norm})")
                
            # ---- Save edge payload (flat; wrapped in final conversion) ----
            self.edges_defuse.append((
                src, dst_sid,
                {
                    "var_key": f"{var}@{src}",
                    "flow_id": fid,
                    "guard_kind": kind,
                    "has_lower_guard": has_lower,
                    "has_upper_guard": has_upper,
                    "upper_guard_norm": upper_norm,
                }
        ))
            

        # Main loop: AST node traversal
        for row in self.nodes:
            sid = row["sid"]
            code = row["code"]
            node_type = row["node_type_id"]

            ensure_feat(sid, node_type)
            node_debug[sid]["code"] = code

            # Per-statement sets
            exclude_vars_stmt: set = set()
            used_by_call_stmt: set = set()

            orig = self._orig_for_stmt(self._find_ast_row_by_sid(sid))

            # [PATCH] Assignment의 RHS에 호출이 있는지 선판단(전역 호출 스캔/플래그 적용을 막기 위함)
            assign_rhs_has_call = False
            rhs_node = None
            if node_type == "AssignmentExpression" and isinstance(orig, dict):
                kids_ = (orig.get("children") or [])
                rhs_node = kids_[1] if len(kids_) >= 2 else None
                if isinstance(rhs_node, dict) and isinstance(self._find_first_call_node(rhs_node), dict):
                    assign_rhs_has_call = True

            # (0) 문장 내부 호출 처리 (컨트롤 노드는 전체 subtree 제외)
            # Special-case: statement-level call nodes may have orig pointing to ParameterList/ArgumentList.
            # In that case, add index-role uses (buffer[i] -> i as index) explicitly.
            # (특수) 문장-수준 호출 노드가 ArgList만 가리키는 경우: 여기서 호출 자체 처리
            if node_type in {"UserDefinedCall","StandardLibCall"} and isinstance(orig, dict) and orig.get("nodeType") in {"ParameterList","ArgumentList"}:
                # 함수명 추출 (memmove(...), fgets(...), ...)

                print(f"(Special) Statement-level call node pointing only to ArgList: handle call here: node = {code}")
                fname = self._callee_name_from_arglist(orig)
                base = (fname or "").lower()

                arg_nodes = (orig.get("children") or [])

                # 1) Argument USE (by role: index/size/base/value)

                for (v, role) in self._call_arg_uses_ast(base, arg_nodes):
                    if role == "base":
                        _add_use_edge(v, "base", sid)   # ← flow_id = 4
                        continue
                    used_by_call_stmt.add(v)
                    _add_use_edge(v, role, sid)

                # 2) Write-effect DEF (dst, etc.)
                for v in self._call_write_effects_ast(base, arg_nodes):
                    if v and v not in KEYWORDS:
                        last_def[v] = sid
                        def_vars_by_sid[sid].add(v)
                        exclude_vars_stmt.add(v)  # exclude dst from token USE

                # 3) Call-based sink/evidence bits
                dst_arg, size_arg = _pick_dst_size_args(base, arg_nodes)

                # dst 인덱싱 여부
                dst_indexed = 1 if self._has_indexing(dst_arg, skip_sizeof=True) else 0

                # len-linked / size nonconst (필드 감도 확장)
                size_txt = (size_arg.get("code") or "") if isinstance(size_arg, dict) else ""
                dst_names = set(self._idents_from_ast_node(dst_arg)) if isinstance(dst_arg, dict) else set()
                dst_full  = self._fullname_from_expr(dst_arg) if isinstance(dst_arg, dict) else None
                if dst_full:
                    dst_names.add(dst_full)

                linked = 0
                if size_txt and dst_names:
                    sizeof_hits = any(
                        ("sizeof(" + dn + ")") in size_txt or
                        ("sizeof(*" + dn + ")") in size_txt or
                        ("sizeof(" + dn + "[0])") in size_txt
                        for dn in dst_names
                    )
                    linked = 1 if sizeof_hits else 0

                # Not recognized as len-linked even if equal to declaration length (v1.11)
                if not linked and dst_names:
                    dst_name = next(iter(dst_names))
                    def _decl_len(var):
                        st = [self.ast_json]
                        import re as _re
                        while st:
                            nn = st.pop()
                            if isinstance(nn, dict) and nn.get("nodeType") == "ArrayDeclaration" and nn.get("name")==var:
                                l = nn.get("length")
                                if isinstance(l, str) and l: return l
                                code0 = nn.get("code","") or ""
                                m0 = _re.search(r"\[\s*(.*?)\s*\]", code0)
                                if m0: return m0.group(1)
                            if isinstance(nn, dict):
                                st.extend([c for c in (nn.get("children") or []) if isinstance(c, dict)])
                        return None
                    decl = _decl_len(dst_name)
                    if decl:
                        import re as _re
                        def _norm(s):
                            s2 = _re.sub(r"\s+", "", s or "")
                            while s2.startswith("(") and s2.endswith(")"):
                                depth=0; ok=True
                                for i,ch in enumerate(s2):
                                    if ch=='(':
                                        depth+=1
                                    elif ch==')':
                                        depth-=1
                                        if depth==0 and i!=len(s2)-1:
                                            ok=False; break
                                if ok: s2=s2[1:-1]
                                else: break
                            return s2
                        if _norm(size_txt) == _norm(decl):
                            # no-op: equality with declaration size does NOT imply len-linked
                            # (optional) you may record a separate bit like: node_feat[sid]["call_len_matches_decl"]=1
                            pass

                size_txt_wo_sizeof = re.sub(r'\bsizeof\s*\([^)]*\)', '', size_txt)
                nonconst = 1 if (size_txt and re.search(r'[A-Za-z_]\w*', size_txt_wo_sizeof)) else 0
                if size_txt and ("sizeof(" in size_txt):
                    # If no sizeof related to dst, then non-dst
                    if not any(("sizeof(" + dn + ")") in size_txt for dn in dst_names):
                        nonconst = 1
                    # If dst is base.field but size is sizeof(base), explicitly non-dst
                    if dst_full and "." in dst_full:
                        base_only = dst_full.split(".")[0]
                        if ("sizeof(" + base_only + ")") in size_txt:
                            nonconst = 1

                if base in UNBOUNDED:
                    node_feat[sid]["is_sink_call_unbounded"] = 1
                    node_feat[sid]["call_danger_unbounded"] = 1
                    node_feat[sid]["call_dst_indexed"] = max(node_feat[sid]["call_dst_indexed"], dst_indexed)
                elif base in BOUNDED:
                    node_feat[sid]["is_sink_call_bounded"] = 1
                    node_feat[sid]["call_dst_indexed"] = max(node_feat[sid]["call_dst_indexed"], dst_indexed)
                    node_feat[sid]["call_len_linked_to_dst"] = max(node_feat[sid]["call_len_linked_to_dst"], linked)
                    node_feat[sid]["call_size_nonconst"] = max(node_feat[sid]["call_size_nonconst"], nonconst)

                # Call node completed here -> skip generic scan
                # We fully handled this statement-level call (roles, DEFs, flags).
                # Skip generic value-scan to avoid double-counting.
                continue

 
            # Prepare sets for preventing call/base-token duplicates in statement scope
            exclude_vars_stmt: Set[str] = set()
            used_by_call_stmt: Set[str] = set()

            # (0) Handle calls within generic statements
            if isinstance(orig, dict) and (node_type not in CONTROL_NODES):
                 
                # [PATCH] 대입식이고 RHS에 호출이 있으면, 호출 인자/쓰기효과/플래그를 "대입 노드"에 붙이지 않음
                if assign_rhs_has_call:
                    pass  # Call->assignment edge added in 3) below
                else:
                    print(f"node_type not in CONTROL_NODES : node = {code}")

                    for fname, arg_nodes in self._iter_calls_ast(orig):
                        base = (fname or "").lower()

                        # Argument USE (role mapping)
                        for (v, role) in self._call_arg_uses_ast(fname, arg_nodes):
                            if role == "base":
                                _add_use_edge(v, "base", sid)   # <- flow_id = 4 edge creation
                                continue
                            used_by_call_stmt.add(v)
                            _add_use_edge(v, role, sid)



                        # Write-effect DEF (dst, etc.)
                        for v in self._call_write_effects_ast(fname, arg_nodes):
                            if v and v not in KEYWORDS:
                                last_def[v] = sid
                                def_vars_by_sid[sid].add(v)
                                exclude_vars_stmt.add(v)  # exclude dst from token USE

                        # ---- Call-based sink/evidence bits ----
                        dst_arg, size_arg = _pick_dst_size_args(base, arg_nodes)

                        # Whether dst is indexed
                        dst_indexed = 1 if self._has_indexing(dst_arg, skip_sizeof=True) else 0

                        # len-linked / size nonconst (field sensitivity extension)
                        size_txt = (size_arg.get("code") or "") if isinstance(size_arg, dict) else ""
                        dst_names = set(self._idents_from_ast_node(dst_arg)) if isinstance(dst_arg, dict) else set()
                        dst_full  = self._fullname_from_expr(dst_arg) if isinstance(dst_arg, dict) else None
                        if dst_full:
                            dst_names.add(dst_full)

                        linked = 0
                        if size_txt and dst_names:
                            sizeof_hits = any(
                                ("sizeof(" + dn + ")") in size_txt or
                                ("sizeof(*" + dn + ")") in size_txt or
                                ("sizeof(" + dn + "[0])") in size_txt
                                for dn in dst_names
                            )
                            linked = 1 if sizeof_hits else 0

                        # Not considered len-linked if equal to declaration length (v1.11)
                        if not linked and dst_names:
                            dst_name = next(iter(dst_names))
                            def _decl_len(var):
                                st = [self.ast_json]
                                import re as _re
                                while st:
                                    nn = st.pop()
                                    if isinstance(nn, dict) and nn.get("nodeType") == "ArrayDeclaration" and nn.get("name")==var:
                                        l = nn.get("length")
                                        if isinstance(l, str) and l: return l
                                        code0 = nn.get("code","") or ""
                                        m0 = _re.search(r"\[\s*(.*?)\s*\]", code0)
                                        if m0: return m0.group(1)
                                    if isinstance(nn, dict):
                                        st.extend([c for c in (nn.get("children") or []) if isinstance(c, dict)])
                                return None
                            decl = _decl_len(dst_name)
                            if decl:
                                import re as _re
                                def _norm(s):
                                    s2 = _re.sub(r"\s+", "", s or "")
                                    while s2.startswith("(") and s2.endswith(")"):
                                        depth=0; ok=True
                                        for i,ch in enumerate(s2):
                                            if ch=='(':
                                                depth+=1
                                            elif ch==')':
                                                depth-=1
                                                if depth==0 and i!=len(s2)-1:
                                                    ok=False; break
                                        if ok: s2=s2[1:-1]
                                        else: break
                                    return s2
                                if _norm(size_txt) == _norm(decl):
                                    # no-op: equality with declaration size does NOT imply len-linked
                                    # (optional) node_feat[sid]["call_len_matches_decl"]=1
                                    pass

                        size_txt_wo_sizeof = re.sub(r'\bsizeof\s*\([^)]*\)', '', size_txt)
                        nonconst = 1 if (size_txt and re.search(r'[A-Za-z_]\w*', size_txt_wo_sizeof)) else 0
                        if size_txt and ("sizeof(" in size_txt):
                            if not any(("sizeof(" + dn + ")") in size_txt for dn in dst_names):
                                nonconst = 1
                            if dst_full and "." in dst_full:
                                base_only = dst_full.split(".")[0]
                                if ("sizeof(" + base_only + ")") in size_txt:
                                    nonconst = 1

                        if base in UNBOUNDED:
                            node_feat[sid]["is_sink_call_unbounded"] = 1
                            node_feat[sid]["call_danger_unbounded"] = 1
                            node_feat[sid]["call_dst_indexed"] = max(node_feat[sid]["call_dst_indexed"], dst_indexed)
                        elif base in BOUNDED:
                            node_feat[sid]["is_sink_call_bounded"] = 1
                            node_feat[sid]["call_dst_indexed"] = max(node_feat[sid]["call_dst_indexed"], dst_indexed)
                            node_feat[sid]["call_len_linked_to_dst"] = max(node_feat[sid]["call_len_linked_to_dst"], linked)
                            node_feat[sid]["call_size_nonconst"] = max(node_feat[sid]["call_size_nonconst"], nonconst)
                        
                    # Call statement ends here -> (5) prevent generic value scan
                    if node_type in {"UserDefinedCall", "StandardLibCall", "CallExpression"}:
                        continue


            # (1) Control nodes: process condition subtree and exit
            if node_type in CONTROL_NODES and isinstance(orig, dict):
                cond_node = self._get_condition_node(node_type, orig)
                if cond_node is not None:
                     
                    # ForStatement header DEF seeding (i=0, i++, i+=k, etc. -> recognize i as DEF)
                    def_names: Set[str] = set()
                    if node_type == "ForStatement":
                        kids = (orig.get("children") or [])
                        init = kids[0] if len(kids) >= 1 else None
                        inc  = kids[2] if len(kids) >= 3 else None

                        def_names: Set[str] = set()

                        # 1) Init: i = <expr> -> recognize LHS identifier as DEF
                        if isinstance(init, dict) and init.get("nodeType") == "AssignmentExpression":
                            lhs, rhs = (init.get("children") or [None, None])[:2]
                            if isinstance(lhs, dict) and lhs.get("nodeType") == "Identifier":
                                nm = lhs.get("name")
                                if isinstance(nm, str) and nm and nm not in KEYWORDS:
                                    def_names.add(nm)

                        # 2) Increment/Decrement: ++i, i++, --i, i--, i += k, etc. -> extract from inc expression as DEF
                        if isinstance(inc, dict):
                            for t in self._idents_from_ast_node(inc, skip_sizeof=True, skip_callee=True):
                                if t and t not in KEYWORDS:
                                    def_names.add(t)

                        # 3) Apply DEF (update last_def before condition USE/call processing)
                        for v in sorted(def_names):
                            last_def[v] = sid
                            def_vars_by_sid[sid].add(v)
        
                    # Control nodes do not reflect call-based write/sink/len-linked bits
                    nf = node_feat[sid]
                    nf["is_buffer_access"] = 0
                    nf["is_sink_assign"] = 0
                    nf["is_sink_call_unbounded"] = 0
                    nf["is_sink_call_bounded"] = 0
                    nf["call_dst_indexed"] = 0
                    nf["call_len_linked_to_dst"] = 0
                    nf["call_size_nonconst"] = 0
                    nf["call_danger_unbounded"] = 0

                    nf["def_count"] = len(def_vars_by_sid[sid])
                    nf["use_count"] = len(use_vars_by_sid[sid])

                continue

            # (2) Decl
            if node_type in {"VariableDeclaration","ParameterDeclaration", "PointerDeclaration"} and isinstance(orig, dict):
                nm = orig.get("name")
                if isinstance(nm, str) and nm and nm not in KEYWORDS:
                    last_def[nm] = sid
                    def_vars_by_sid[sid].add(nm)
                continue

            # (3) Assignment
            if node_type == "AssignmentExpression" and isinstance(orig, dict):
                # LHS buffer[INDEX] -> pre-process INDEX as role="index" (preserve guard/var_key)
                chs = (orig.get("children") or [])
                lhs = chs[0] if len(chs) >= 1 else None
                if isinstance(lhs, dict) and lhs.get("nodeType") == "ArraySubscriptExpression":
                    kids = lhs.get("children") or []
                    idx  = kids[1] if len(kids) > 1 else None
                    if isinstance(idx, dict):
                        for v in self._idents_from_ast_node(idx, skip_sizeof=True, skip_callee=True):
                            if v:
                                _add_use_edge(v, "index", sid)

               
                # 3-0) Check LHS form: ArraySubscript / PointerDereference / Identifier / MemberAccess
                chs = (orig.get("children") or [])
                lhs = chs[0] if len(chs) >= 1 else None
                lhs_base_name = None
                lhs_nt = None
                lhs_is_pointer_base = False   # 'Base read' write (e.g., data[i], *p)
                lhs_is_object_base  = False   # 'Object write' (DEF) (e.g., buffer[i], s.field, data)

                if isinstance(lhs, dict):
                    lhs_nt = lhs.get("nodeType")
                    if lhs_nt == "ArraySubscriptExpression":
                        kids = lhs.get("children") or []
                        base = kids[0] if len(kids) > 0 else None
                        if isinstance(base, dict):
                            lhs_base_name = self._fullname_from_expr(base)
                            if not lhs_base_name and base.get("nodeType") == "Identifier":
                                lhs_base_name = base.get("name")
   
                        print(f"ArraySubscriptExpression - code: {code}, lhs_base_name : {lhs_base_name}")

                        # Whether it's a pointer base
                        if isinstance(base, dict) and base.get("nodeType") == "PointerDereference":
                            lhs_is_pointer_base = True

                        print(f"ArraySubscriptExpression - code: {code}, lhs_is_pointer_base : {lhs_is_pointer_base}")

                        # Whether it's an object base: arrays/fields, etc. (treated as object if not in pointer_vars and is Identifier/MemberAccess)
                        if not lhs_is_pointer_base:
                            if isinstance(base, dict) and base.get("nodeType") in {"Identifier","MemberAccess"}:
                                lhs_is_object_base = True

                    elif lhs_nt == "PointerDereference":
                        inner = (lhs.get("children") or [None])[0]
                        if isinstance(inner, dict):
                            lhs_base_name = self._fullname_from_expr(inner)
                            if not lhs_base_name and inner.get("nodeType") == "Identifier":
                                lhs_base_name = inner.get("name")
                        
                        # Check if true dereference: only if code starts with '*'
                        lhs_code = (lhs.get("code") or "").strip()
                        is_true_deref = lhs_code.startswith("*")
                        if is_true_deref:
                            lhs_is_pointer_base = True   # *p = ...
                        else:
                            # 'data = ...' wrapped in PointerDereference -> treated as variable assignment
                            lhs_is_object_base = True

                    elif lhs_nt in {"Identifier","MemberAccess"}:
                        lhs_base_name = self._fullname_from_expr(lhs) or lhs.get("name")
                        # 단독 LHS가 식별자/필드면 객체(변수 자체에 쓰기)
                        lhs_is_object_base = True

                # 3-1) Basic assignment extraction
                def_vars, uses, iba, sink = self._assignment_by_ast(orig, sid)

                # 3-2) LHS base processing policy
                #   - Pointer base (data[i], *p): No DEF, only USE(base)
                #   - Object base (buffer[i], s.field): Keep DEF, remove base USE
                if lhs_base_name and lhs_base_name not in KEYWORDS:
                    if lhs_is_object_base:
                        # (A) Write to object (base): keep DEF
                        if lhs_base_name not in def_vars:
                            def_vars.append(lhs_base_name)

                        # Container write (index/field): BASE(4) edge + guard aggregate injection
                        if lhs_nt in {"ArraySubscriptExpression", "MemberAccess"}:
                            # Collect index variables
                            idx_vars = []
                            if lhs_nt == "ArraySubscriptExpression":
                                kids = lhs.get("children") or []
                                idx  = kids[1] if len(kids) > 1 else None
                                if isinstance(idx, dict):
                                    idx_vars = self._idents_from_ast_node(idx, skip_sizeof=True, skip_callee=True)

                            # Synthesize guards for current sid from variable/aggregate as fallback
                            gm_here = self.guard_map.get(sid, {})
                            agg = {"kind": 0, "lower": 0, "upper": 0, "upper_const": 0.0}
                            for iv in idx_vars or []:
                                g = (gm_here.get(iv) or gm_here.get("*") or gm_here.get("__agg__") or {})
                                agg["lower"] |= int(g.get("lower", 0))
                                agg["upper"] |= int(g.get("upper", 0))
                                agg["upper_const"] = max(agg["upper_const"], float(g.get("upper_const", 0.0)))
                                if not agg["kind"]:
                                    agg["kind"] = int(g.get("kind", 0))
                            if not agg["kind"]:
                                gf = (gm_here.get("*") or gm_here.get("__agg__") or {})
                                agg["kind"] = int(gf.get("kind", 0))
                                agg["lower"] |= int(gf.get("lower", 0))
                                agg["upper"] |= int(gf.get("upper", 0))
                                agg["upper_const"] = max(agg["upper_const"], float(gf.get("upper_const", 0.0)))

                            # Inject synthesis result into fallback slot of dst statement sid
                            gm_dst = self.guard_map.setdefault(sid, {})
                            gm_dst["*"] = {"kind": agg["kind"], "lower": agg["lower"], "upper": agg["upper"], "upper_const": agg["upper_const"]}
                            gm_dst["__agg__"] = gm_dst["*"]

                            # BASE(4) edge + guard aggregate injection (must call before last_def update for correct var_key)
                            _add_use_edge(lhs_base_name, "base", sid)    
                      
                        
                        # Remove if base token was double-counted as USE
                        # Remove base USE in object write statements (may have been added by earlier extraction)
                        uses = [(v,r) for (v,r) in uses if not (v == lhs_base_name and r == "base")]
                    
                    
                    
                    elif lhs_is_pointer_base:
                        # If pointer base, do not treat as DEF (remove from def_vars)
                        # (B) Pointer base: No DEF, keep base USE
                        def_vars = [dv for dv in def_vars if dv != lhs_base_name]
                        # Add base USE if missing
                        if (lhs_base_name, "base") not in uses:
                            uses.append((lhs_base_name, "base"))


                # 3-3) Perform only duplicate prevention with call-based tokens (keep base -> preserve flow_id=4)
                # If RHS contains a call, assignment should not own RHS 'value' uses (split call node owns them)
                try:
                    chs_rhs = (orig.get("children") or [])
                    rhs = chs_rhs[1] if len(chs_rhs) >= 2 else None
                    rhs_call = self._find_first_call_node(rhs) if isinstance(rhs, dict) else None
                    if isinstance(rhs_call, dict):
                        uses = [(v,r) for (v,r) in uses if r != "value"]
                except Exception:
                    pass
                uses = [
                    (v, r)
                    for (v, r) in uses
                    if v not in exclude_vars_stmt and v not in used_by_call_stmt
                ]

                for (v, role) in uses:
                    _add_use_edge(v, role, sid)
                for dv in def_vars:
                    if dv and dv not in KEYWORDS:
                        last_def[dv] = sid
                        def_vars_by_sid[sid].add(dv)
                # --- RHS call split handling: add call→assign value-flow edge
                try:
                    chs2 = (orig.get("children") or [])
                    rhs2 = chs2[1] if len(chs2) >= 2 else None
                    calln = self._find_first_call_node(rhs2) if isinstance(rhs2, dict) else None
                    if isinstance(calln, dict):
                        cid = calln.get("id")
                        sid_call = self.orig2sid.get(cid)
                        if isinstance(sid_call, int) and self._sb_has(sid_call, sid):
                            gi = (self.guard_map.get(sid) or {}).get("__agg__", {})
                            self.edges_defuse.append((
                                sid_call, sid,
                                {
                                    "var_key": f"$ret@{sid_call}",
                                    "feat": {"flow_id": FLOW_ID["value"],
                                             "guard_kind": int(gi.get("kind",0)),
                                             "has_lower_guard": int(gi.get("lower",0)),
                                             "has_upper_guard": int(gi.get("upper",0)),
                                             "upper_guard_norm": float(gi.get("upper_const",0.0))},
                                    "debug": {"var_key": f"$ret@{sid_call}"}
                                }
                            ))
                except Exception:
                    pass

                if iba: iba_by_sid[sid] = 1
                if sink: sink_assign_by_sid[sid] = 1
                continue

            # (4) ArrayDecl / ArraySizeAllocation
            if node_type in {"ArrayDeclaration", "ArraySizeAllocation"} and isinstance(orig, dict):
                def_vars, uses = self._array_decl_by_ast(orig)
                for (v, role) in uses:
                    _add_use_edge(v, role, sid)
                for dv in def_vars:
                    if dv and dv not in KEYWORDS:
                        last_def[dv] = sid
                        def_vars_by_sid[sid].add(dv)
                continue

            # (5) Other statements: value USE (excluding callee/sizeof)
            if isinstance(orig, dict):
                scan_node = orig
                if node_type == "AssignmentExpression":
                    chs = (orig.get("children") or [])
                    lhs = chs[0] if len(chs)>=1 else None
                    rhs = chs[1] if len(chs)>=2 else None
                    if isinstance(rhs, dict) and isinstance(self._find_first_call_node(rhs), dict):
                        scan_node = lhs if isinstance(lhs, dict) else orig
                for t in self._idents_from_ast_node(scan_node, skip_sizeof=True, skip_callee=True):
                    if t in exclude_vars_stmt or t in used_by_call_stmt:
                        continue
                    _add_use_edge(t, "value", sid)

        # Degree aggregation
        deg_in = {n["sid"]:0 for n in self.nodes}
        deg_out = {n["sid"]:0 for n in self.nodes}
        for (s,d,_) in self.edges_defuse:
            if s in deg_out: deg_out[s] += 1
            if d in deg_in:  deg_in[d] += 1

        # Synchronize final nodes (feat/debug)
        out_nodes: List[Dict[str,Any]] = []
        for meta in self.nodes:
            sid = meta["sid"]
            code = meta["code"]
            node_type = meta["node_type_id"]

            ensure_feat(sid, node_type)

            # Adjust use list for Assignment with RHS call: remove RHS identifiers (owned by split call node)
            ulist = sorted([x for x in use_vars_by_sid.get(sid, set()) if x and x != "<empty>"])
            try:
                if node_type == "AssignmentExpression":
                    row = self.sid2flat.get(sid, {}) or {}
                    oid = row.get("orig_id")
                    an = self.idmap.get(oid) if isinstance(oid, int) else None
                    kids = an.get("children") or [] if isinstance(an, dict) else []
                    rhs = kids[1] if len(kids) >= 2 else None
                    if isinstance(rhs, dict) and isinstance(self._find_first_call_node(rhs), dict):
                        rhs_idents = set(self._idents_from_ast_node(rhs, skip_sizeof=True, skip_callee=True))
                        ulist = [x for x in ulist if x not in rhs_idents]
            except Exception:
                pass
            dlist = sorted([x for x in def_vars_by_sid.get(sid, set()) if x and x != "<empty>"])

            feat = node_feat[sid]
            feat["in_degree_dfg"]  = deg_in.get(sid, 0)
            feat["out_degree_dfg"] = deg_out.get(sid, 0)
            feat["def_count"] = len(dlist)
            feat["use_count"] = len(ulist) # base 제외된 목록 기준
            feat["is_buffer_access"] = 1 if iba_by_sid.get(sid,0) else 0
            feat["is_sink_assign"] = 1 if sink_assign_by_sid.get(sid,0) else 0

            # Ensure AssignmentExpression is call-neutral
            if node_type == "AssignmentExpression":
                feat["is_sink_call_unbounded"] = 0
                feat["is_sink_call_bounded"] = 0
                feat["call_dst_indexed"] = 0
                feat["call_len_linked_to_dst"] = 0
                feat["call_size_nonconst"] = 0
                feat["call_danger_unbounded"] = 0


            dbg = node_debug[sid]
            dbg["code"] = code
            dbg["def_vars"] = dlist
            dbg["use_vars"] = ulist

            out_nodes.append({"sid": sid, "feat": feat, "debug": dbg})

        # 최종 에지: feat/debug 분리 변환
        out_edges: List[List[Any]] = []
        for (s, d, attr) in self.edges_defuse:
            out_edges.append([
                s, d,
                {
                    "feat": {
                        "flow_id": attr.get("flow_id", 1),
                        "guard_kind": attr.get("guard_kind", 0),
                        "has_lower_guard": attr.get("has_lower_guard", 0),
                        "has_upper_guard": attr.get("has_upper_guard", 0),
                        "upper_guard_norm": attr.get("upper_guard_norm", 0.0),
                    },
                    "debug": {
                        "var_key": attr.get("var_key","")
                    }
                }
            ])

        return {"nodes": out_nodes, "edges_dfg": out_edges}



    # -----------------------------------------------------------------
    # End of run function
    # ----------------------------------------------------------------   

    # ------------------------------
    # AST helpers / schema-based visitors
    # ------------------------------
    def _find_ast_row_by_sid(self, sid: int) -> Dict[str, Any] | None:
        """Return flattened AST row by sid (has orig_id/id/code/node_type_id)."""
        try:
            s = int(sid)
        except Exception:
            return None
        return self.sid2flat.get(s)

    def _orig_for_stmt(self, flat_row: Dict[str,Any] | None) -> Dict[str,Any] | None:
        if not isinstance(flat_row, dict):
            return None
        orig_id = flat_row.get("orig_id") if isinstance(flat_row.get("orig_id"), int) else None
        if orig_id is None:
            # Some pipelines may preserve id even in flattened rows
            alt = flat_row.get("id")
            orig_id = alt if isinstance(alt, int) else None
        return self.id2orig.get(orig_id)

    def _index_ast_by_id(self, node: Any) -> Dict[int,Dict[str,Any]]:
        out: Dict[int,Dict[str,Any]] = {}
        def walk(n: Any):
            if isinstance(n, dict):
                nid = n.get("id")
                if isinstance(nid, int):
                    out[nid] = n
                for c in n.get("children", []) or []:
                    walk(c)
            elif isinstance(n, list):
                for c in n: walk(c)
        walk(node)
        return out

    def _collect_param_names(self, ast_json: Dict[str,Any]) -> List[str]:
        names: List[str] = []
        def walk(node: Any):
            if isinstance(node, dict):
                if node.get("nodeType") == "ParameterDeclaration":
                    nm = node.get("name")
                    if isinstance(nm, str) and nm:
                        names.append(nm)
                for ch in node.get("children", []) or []:
                    walk(ch)
            elif isinstance(node, list):
                for it in node: walk(it)
        walk(ast_json)
        # 순서보존 dedupe
        seen:set = set(); out:List[str] = []
        for nm in names:
            # Exclude empty strings/placeholders + remove duplicates
            if nm and nm != "<empty>" and nm not in seen:
                seen.add(nm); out.append(nm)
        return out


    def _get_condition_node(self, node_type: str, ast_node: dict):
        """
        Returns the 'condition expression' subtree from control statement AST nodes.
        - If: children[0]
        - For: children[1]   <- (init, cond, inc)
        - While: children[0]
        - Do/DoWhile: Last non-CompoundStatement
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
        if node_type in {"DoWhileStatement","DoStatement"}:
            for k in reversed(kids):
                if isinstance(k, dict) and k.get("nodeType") != "CompoundStatement":
                    return k
            return None
        return None
    
    # --------------------------------------------------------------------
    # Field-sensitive helpers (MemberAccess / MemberExpression)
    # --------------------------------------------------------------------
    def _is_member_access(self, n):
        return isinstance(n, dict) and n.get("nodeType") == "MemberAccess"

    def _member_parts(self, n):
        """Return (base_name, field_name, full_name='base.field') for a member access node."""
        if not self._is_member_access(n):
            return None, None, None
        kids = n.get("children") or []
        base = kids[0] if len(kids) > 0 else None
        field = kids[1] if len(kids) > 1 else None
        base_name = base.get("name") if isinstance(base, dict) and base.get("nodeType") == "Identifier" else None
        field_name = field.get("name") if isinstance(field, dict) and field.get("nodeType") == "Identifier" else None
        full = f"{base_name}.{field_name}" if base_name and field_name else None
        return base_name, field_name, full

    def _unwrap_cast_paren(self, n):
        """Peel Cast/Paren wrappers to reach the core expression."""
        while isinstance(n, dict) and n.get("nodeType") in {"CastExpression","CStyleCastExpr","ParenExpression","ParenExpr"}:
            kids = n.get("children") or []
            n = kids[0] if kids else n
        return n

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
            n.get("nodeType") == "PointerDereference" or
            (n.get("nodeType") in {"UnaryOperator","UnaryExpression"} and n.get("operator") in {"*","&"})
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


    # ------------------------------
    # PointerDeclaration 수집
    # ------------------------------
    def _collect_pointer_names(self, ast_json: Dict[str,Any]) -> Set[str]:
        names: Set[str] = set()
        def walk(node):
            if isinstance(node, dict):
                if node.get("nodeType") == "PointerDeclaration":
                    nm = node.get("name")
                    if isinstance(nm, str) and nm:
                        names.add(nm)
                for ch in (node.get("children") or []):
                    walk(ch)
            elif isinstance(node, list):
                for it in node:
                    walk(it)
        walk(ast_json)
        return names



    def _find_enclosing_call_for(self, node: dict) -> dict | None:
        """ParameterList/ArgumentList 노드의 상위 CallExpression을 찾아 반환."""
        if not isinstance(node, dict):
            return None
        target = node
        target_id = node.get("id") or node.get("orig_id")
        stack = [self.ast_json]
        while stack:
            n = stack.pop()
            if not isinstance(n, dict):
                continue
            if n.get("nodeType") in {"StandardLibCall","UserDefinedCall","CallExpression"}:
                for c in (n.get("children") or []):
                    if not isinstance(c, dict):
                        continue
                    if c is target:
                        return n
                    cid = c.get("id") or c.get("orig_id")
                    if target_id is not None and cid is not None and cid == target_id:
                        return n
            stack.extend([c for c in (n.get("children") or []) if isinstance(c, dict)])
        return None

    def _callee_name_from_arglist(self, arglist_node: dict) -> str:
        """ParameterList/ArgumentList에서 callee 이름을 AST의 name으로 가져옴.
        CallExpression.name이 없으면 첫 자식 Identifier.name 사용."""
        call = self._find_enclosing_call_for(arglist_node)
        if not isinstance(call, dict):
            return ""
        nm = call.get("name")
        if isinstance(nm, str) and nm:
            return nm
        kids = call.get("children") or []
        if kids and isinstance(kids[0], dict) and kids[0].get("nodeType") == "Identifier":
            nm2 = kids[0].get("name")
            if isinstance(nm2, str) and nm2:
                return nm2
        return ""


    def _iter_calls_ast(self, node: Dict[str,Any]):

        def walk(n: Any):
            if not isinstance(n, dict):
                return
            nt = n.get("nodeType")
            kids = n.get("children", []) or []

            if nt == "CallExpression":
                callee = kids[0] if kids else None
                fname = callee.get("name") if isinstance(callee, dict) and callee.get("nodeType")=="Identifier" else ""
                args = kids[1:] if len(kids) > 1 else []
                yield (fname, args)
                for a in args: yield from walk(a)

            elif nt in {"StandardLibCall","UserDefinedCall"}:
                fname = n.get("name") or ""
                # ParameterList / ArgumentList 중 하나를 찾아 인자들 추출
                plist = next((c for c in kids if isinstance(c, dict) and c.get("nodeType") in {"ParameterList","ArgumentList"}), None)
                args = (plist.get("children", []) if isinstance(plist, dict) else [])
                yield (fname, args)
                for a in args: yield from walk(a)
            else:
                for ch in kids: yield from walk(ch)
        yield from walk(node)

    def _idents_from_ast_node(
        self,
        node: Dict[str, Any] | None,
        *,
        skip_sizeof: bool = True,
        skip_callee: bool = True
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
        names: List[str] = []

        def _member_full_name(n: Dict[str, Any]) -> str | None:
            if not isinstance(n, dict):
                return None
            nt = n.get("nodeType")
            if nt == "MemberAccess":
                kids = (n.get("children") or [])
                base = kids[0] if len(kids) > 0 else None
                field = kids[1] if len(kids) > 1 else None
                base_full = _member_full_name(base) or (
                    base.get("name") if isinstance(base, dict) and base.get("nodeType") == "Identifier" else None
                )
                field_name = field.get("name") if isinstance(field, dict) and field.get("nodeType") == "Identifier" else None
                if base_full and field_name:
                    return f"{base_full}.{field_name}"
                return None
            elif nt == "Identifier":
                nm = n.get("name")
                return nm if isinstance(nm, str) and nm and nm not in KEYWORDS else None
            else:
                return None

        def _is_macro_const_call(n: Dict[str, Any]) -> bool:
            """
            UserDefinedCall 하위에 존재하는 (ParameterList|ArgumentList)들 중
            하나라도 CompoundStatement를 후손으로 가지면 '매크로-상수 호출'로 판단한다.

            예) StandardLibCall(inet_addr)
                └─ ParameterList
                └─ UserDefinedCall(IP_ADDRESS)
                    └─ ParameterList
                        └─ CompoundStatement
                            └─ Literal "127.0.0.1"
            """
            if not isinstance(n, dict) or n.get("nodeType") != "UserDefinedCall":
                return False

            # 1) UDC 하위의 모든 (ParameterList|ArgumentList)를 수집
            lists = []
            stack = list(n.get("children") or [])
            while stack:
                z = stack.pop()
                if not isinstance(z, dict):
                    continue
                nt = z.get("nodeType")
                if nt in {"ParameterList", "ArgumentList"}:
                    lists.append(z)
                for c in (z.get("children") or []):
                    if isinstance(c, dict):
                        stack.append(c)

            if not lists:
                return False

            # 2) 각 리스트의 후손에 CompoundStatement가 있는지 탐색
            def _has_compound(desc: Dict[str, Any]) -> bool:
                st = [desc]
                while st:
                    x = st.pop()
                    if not isinstance(x, dict):
                        continue
                    if x.get("nodeType") == "CompoundStatement":
                        return True
                    for cc in (x.get("children") or []):
                        if isinstance(cc, dict):
                            st.append(cc)
                return False

            for pl in lists:
                if _has_compound(pl):
                    return True
            return False
        
        

        def walk(n: Any, under_sizeof: bool = False):
            if not isinstance(n, dict):
                return
            nt = n.get("nodeType")

            # sizeof(...) 내부는 USE로 세지 않음
            if nt == "SizeOfExpression":
                for c in n.get("children", []) or []:
                    walk(c, True if skip_sizeof else under_sizeof)
                return

            # 호출 노드
            if nt in {"StandardLibCall", "UserDefinedCall", "CallExpression"}:
                # 매크로 상수 의사 호출이면 통째로 무시
                if nt == "UserDefinedCall" and _is_macro_const_call(n):
                    return
                # 첫 자식(callee) 스킵
                first = True
                for c in n.get("children", []) or []:
                    if first and skip_callee and isinstance(c, dict) and c.get("nodeType") == "Identifier":
                        first = False
                        continue
                    first = False
                    walk(c, under_sizeof)
                return

            # 필드 접근은 풀네임 1토큰으로 수집
            if nt == "MemberAccess":
                if not under_sizeof:
                    full = _member_full_name(n)
                    if full and full not in KEYWORDS:
                        names.append(full)
                return

            if nt == "Identifier":
                nm = n.get("name")
                if isinstance(nm, str) and nm and nm not in KEYWORDS and not under_sizeof:
                    names.append(nm)

            for c in n.get("children", []) or []:
                walk(c, under_sizeof)

        walk(node, False)
        # 순서보존 dedupe
        seen: set = set(); out: List[str] = []
        for nm in names:
            if nm not in seen:
                seen.add(nm); out.append(nm)
        return out


    def _has_indexing(self, node: Dict[str,Any] | None, *, skip_sizeof: bool = True) -> bool:
        found = False
        def walk(n: Any, under_sizeof: bool = False):
            nonlocal found
            if found or not isinstance(n, dict):
                return
            nt = n.get("nodeType")
            if nt == "SizeOfExpression":
                for c in n.get("children", []) or []:
                    walk(c, True if skip_sizeof else under_sizeof)
                return
            if nt == "ArraySubscriptExpression":
                found = True; return
            # *(p+i) 같은 포인터 간접의 단순 패턴 (Unary * + Binary +|-)
            if nt in {"UnaryOperator","UnaryExpression"} and n.get("operator") == "*":
                for ch in n.get("children", []) or []:
                    if isinstance(ch, dict) and ch.get("nodeType") == "BinaryExpression" and ch.get("operator") in {"+","-"}:
                        found = True; return
            for c in n.get("children", []) or []:
                walk(c, under_sizeof)
        walk(node, False)
        return found
    

    #선언 초기화 번들 감지 헬퍼 
    #패턴으로 name[...] = { (배열 브레이스 초기화) 또는 name[...] = "..."(문자열 리터럴 초기화)를 체크
    #그리고 직전 1~2개 평탄화 노드가 ArrayDeclaration/ArraySizeAllocation이며 이름이 같은지 확인 (번들 구조 보완)
    def _is_decl_init_trick(self, sid: int, name: str, assign_node: Dict[str,Any]) -> bool:
        code = (assign_node.get("code") or "")
        if not name or not code:
            return False
        # Pattern: name[ ... ] = { ... }  or  name[ ... ] = "..."
        pat_brace = r'^\s*' + re.escape(name) + r'\s*\[[^\]]+\]\s*=\s*\{'
        pat_str   = r'^\s*' + re.escape(name) + r'\s*\[[^\]]+\]\s*=\s*\"'
        if re.search(pat_brace, code) or re.search(pat_str, code):
            return True

        # Inspect adjacent flattened nodes (ArrayDecl/ArraySizeAlloc + same name)
        idx = None
        for i, n in enumerate(self.nodes):
            if n["sid"] == sid:
                idx = i; break
        if idx is None:
            return False

        def _name_from_orig(row_sid: int) -> str:
            flat = self._find_ast_row_by_sid(row_sid)
            orig = self._orig_for_stmt(flat)
            if not isinstance(orig, dict):
                return ""
            nm = orig.get("name") if isinstance(orig.get("name"), str) else ""
            if not nm:
                for ch in orig.get("children", []) or []:
                    if isinstance(ch, dict) and ch.get("nodeType") == "Identifier":
                        n2 = ch.get("name")
                        if isinstance(n2, str) and n2:
                            return n2
            return nm or ""

        for j in (idx-1, idx-2):
            if j >= 0:
                nt = self.nodes[j]["node_type_id"]
                if nt in {"ArrayDeclaration","ArraySizeAllocation"}:
                    if _name_from_orig(self.nodes[j]["sid"]) == name:
                        return True
        return False
    

    def _assignment_by_ast(self, assign_node: Dict[str,Any], cur_sid: int) -> Tuple[List[str], List[Tuple[str,str]], int, int]:
        """For AssignmentExpression only: (def_vars, uses[(var,role)], is_buffer_access, is_sink)"""
        def_vars: List[str] = []
        uses: List[Tuple[str,str]] = []
        iba, is_sink = 0, 0
        kids = assign_node.get("children", []) or []
        lhs = kids[0] if len(kids)>=1 else None
        rhs = kids[1] if len(kids)>=2 else None
        base_name: Optional[str] = None

        # --- helper: LHS 텍스트 기반 인덱싱 보조 감지 
        # int buffer[10] = { 0 }; 와 같은 케이스를 지원하기 위함
        # buffer[ ... ] = 패턴이 있으면 is_buffer_access=1로 잡고, 인덱스가 비상수 식별자를 포함하면 is_sink=1
        def _lhs_textual_indexing(node: Dict[str,Any], name: str) -> Tuple[bool, bool]:
            """
            Detect name[ ... ] pattern on the left of '=' in the code string.
            return: (has_indexing, index_has_identifier_for_sink)
            - has_indexing: True if LHS has a subscript
            - index_has_identifier_for_sink: True if identifiers remain after removing sizeof(...)
            """
            code = (node.get("code") or "") if isinstance(node, dict) else ""
            if not code or not name:
                return (False, False)
            left = code.split("=", 1)[0]
            pattern = r'\b' + re.escape(name) + r'\s*\[([^\]]+)\]'
            m = re.search(pattern, left)
            if not m:
                return (False, False)
            idx_expr = m.group(1)
            # Check for identifiers after removing sizeof(...) fragments -> used only for sink determination
            idx_no_sizeof = re.sub(r'\bsizeof\s*\([^)]*\)', '', idx_expr)
            has_ident = bool(re.search(r'[A-Za-z_]\w*', idx_no_sizeof))
            return (True, has_ident)



        if isinstance(lhs, dict) and lhs.get("nodeType") == "ArraySubscriptExpression":
            # print( ... )
            base, index = (lhs.get("children") or [None,None])[:2]
            
            # LHS base = USE(주소 계산), DEF 아님
            if isinstance(base, dict):
                base_full = self._fullname_from_expr(base)  # deref/paren/cast/field까지 내부에서 처리
                if base_full and base_full not in KEYWORDS:
                    uses.append((base_full, "base"))
            # index USE
            has_runtime_index = False
            if isinstance(index, dict):
                # 1) 디버그/에지 생성을 위해 sizeof(...) 내부도 USE로 수집
                for t in self._idents_from_ast_node(index, skip_sizeof=False, skip_callee=True):
                    if t and t not in KEYWORDS:
                        uses.append((t, "index"))

                # 2) 싱크 판정은 '런타임 식별자' 존재 여부로 (sizeof 내부 식별자는 제외)
                for t in self._idents_from_ast_node(index, skip_sizeof=True, skip_callee=True):
                    if t and t not in KEYWORDS:
                        has_runtime_index = True
                        break

            iba = 1
            is_sink = 1 if has_runtime_index else 0  # 인덱스가 런타임 식별자를 포함할 때만

        elif isinstance(lhs, dict) and lhs.get("nodeType") == "Identifier":
            base_name = lhs.get("name")
            if isinstance(base_name, str) and base_name and base_name not in KEYWORDS:
                def_vars.append(base_name)
                _has_idx, _idx_has_ident = _lhs_textual_indexing(assign_node, base_name)
                if _has_idx:
                    # 선언 초기화 번들이면 런타임 접근으로 보지 않음
                    if not self._is_decl_init_trick(cur_sid, base_name, assign_node):
                        iba = 1
                        if _idx_has_ident:
                            is_sink = 1

        else:
            # 기타 LHS 표현식: 첫 식별자 DEF로 보수적 처리
            ids = self._idents_from_ast_node(lhs, skip_sizeof=True, skip_callee=True)
            if ids:
                def_vars.append(ids[0])


        # RHS 분석: 먼저 인덱스(role=index)와 베이스(role=base), 그 다음 value(중복/인덱스 제외)
        rhs_index_vars: Set[str] = set()
        if isinstance(rhs, dict) and rhs.get("nodeType") == "ArraySubscriptExpression":
            rk = rhs.get("children") or []
            rhs_base = rk[0] if len(rk) > 0 else None
            rhs_index = rk[1] if len(rk) > 1 else None
            # base USE (읽기)
            if isinstance(rhs_base, dict):
                rhs_base_full = self._fullname_from_expr(rhs_base)
                if rhs_base_full and rhs_base_full not in KEYWORDS:
                    uses.append((rhs_base_full, "base"))
            # index USE
            if isinstance(rhs_index, dict):
                for t in self._idents_from_ast_node(rhs_index, skip_sizeof=False, skip_callee=True):
                    if t and t not in KEYWORDS:
                        uses.append((t, "index"))
                        rhs_index_vars.add(t)

        return def_vars, uses, iba, is_sink

    def _array_decl_by_ast(self, decl: Dict[str, Any]) -> Tuple[List[str], List[Tuple[str, str]]]:
        """
        ArrayDeclaration / ArraySizeAllocation 처리:
        - def_vars: 배열 식별자
        - uses: 길이식에서 식별자 (단, sizeof(...) 내부는 USE로 세지지 않음)
        """
        def_vars: List[str] = []
        uses: List[Tuple[str, str]] = []

        nt = decl.get("nodeType")
        if nt == "ArrayDeclaration":
            nm = decl.get("name")
            if isinstance(nm, str) and nm and nm not in KEYWORDS:
                def_vars.append(nm)
            # 길이식 추출 (스키마에 따라 children[0] 등)
            kids = decl.get("children") or []
            length = kids[0] if kids else None
            if isinstance(length, dict):
                # ✅ sizeof 내부는 USE로 세지지 않음
                for t in self._idents_from_ast_node(length, skip_sizeof=True, skip_callee=True):
                    if t and t not in KEYWORDS:
                        uses.append((t, "size"))
        elif nt == "ArraySizeAllocation":
            # 필요 시 동일 규칙 적용
            kids = decl.get("children") or []
            length = kids[0] if kids else None
            if isinstance(length, dict):
                for t in self._idents_from_ast_node(length, skip_sizeof=True, skip_callee=True):
                    if t and t not in KEYWORDS:
                        uses.append((t, "size"))

        return def_vars, uses
    
    # ------------------------------
    # Calls: 역할 매핑 (AST 노드 인자)
    # ------------------------------
    def _call_arg_uses_ast(self, fname: str, arg_nodes: List[Dict[str, Any]]) -> List[Tuple[str, str]]:
        """
        호출 인자에서 USE 변수 추출.
        - call_node 내부의 인자들을 역할별로 USE로 수집한다.
        - 역할: value/ index / size / base 
        - ArraySubscriptExpression의 첨자(index) 식별자는 role="index" (※ sizeof(...) 내부 식별자는 제외)
        - API별 size 슬롯의 식별자는 role="size" (※ sizeof(...) 내부 식별자는 제외)


        - dst(목적지) 인자는 role="base" (필드 감도: base.field)
        - 그 밖의 식별자는 role="value"
        - size/index: DFG 에지는 런타임 의존만 생성해야 하므로 sizeof(...) 내부 식별자는 스킵한다.
        """
        out: List[Tuple[str, str]] = []
        seen: Set[Tuple[str, str]] = set()
        index_vars: Set[str] = set()
        size_vars: Set[str] = set()
        base_vars: Set[str] = set()

        def _emit(name: str, role: str):
            if not name or name in KEYWORDS:
                return
            key = (name, role)
            if key not in seen:
                seen.add(key)
                out.append(key)

        low = (fname or "").lower()

        # dst / size 인자 위치 매핑
        dst_pos = None
        size_pos = None
        if low in {"memcpy", "memmove", "strncpy"}:
            dst_pos, size_pos = 0, 2
        elif low in {"snprintf", "vsnprintf"}:
            dst_pos, size_pos = 0, 1
        elif low in {"fgets"}:
            dst_pos, size_pos = 0, 1
        elif low in {"read", "recv"}:
            dst_pos, size_pos = 1, 2
        elif low in {"getline"}:
            dst_pos, size_pos = 0, 1
        elif low in {"memset"}:                      
            #예) memset(&service, 0, sizeof(service))
            dst_pos, size_pos = 0, 2  ; 
        elif low in {"connect"}:
            # connect(int sockfd, const struct sockaddr *addr, socklen_t addrlen)
            # 예) connect(connectSocket, (struct sockaddr*)&service, sizeof(service)/
            # addr는 입력 포인터(쓰기 대상 아님) → dst_pos=None
            # addrlen은 size 성격 → size_pos=2
            dst_pos, size_pos = None, 2  

        # 1) 모든 인자에서 배열 첨자(index) 먼저 수집 (sizeof 내부 식별자는 제외)
        for a in arg_nodes or []:
            if isinstance(a, dict) and a.get("nodeType") == "ArraySubscriptExpression":
                kids = a.get("children") or []
                idx_node = kids[1] if len(kids) > 1 else None
                if isinstance(idx_node, dict):                   
                    for t in self._idents_from_ast_node(idx_node, skip_sizeof=True, skip_callee=True):
                        _emit(t, "index")
                        index_vars.add(t)

        # 2) size 슬롯 처리: sizeof(...) 내부 식별자는 제외 (런타임 의존만 수집)
        if size_pos is not None and 0 <= size_pos < len(arg_nodes or []):
            size_arg = arg_nodes[size_pos]
            if isinstance(size_arg, dict):               
                for t in self._idents_from_ast_node(size_arg, skip_sizeof=True, skip_callee=True):
                    _emit(t, "size")
                    size_vars.add(t)

        # 3) dst 슬롯 처리: 목적지(base) 표기 (필드 감도)
        if dst_pos is not None and 0 <= dst_pos < len(arg_nodes or []):
            dst_arg = arg_nodes[dst_pos]
            if isinstance(dst_arg, dict):
                for t in self._idents_from_ast_node(dst_arg, skip_sizeof=True, skip_callee=True):
                    print (f"fname = {fname}, Dest Postion!!!!!!")
                    _emit(t, "base")

                    base_vars.add(t)

        # 4) 나머지 인자들: value 표기
        for i, a in enumerate(arg_nodes or []):
            if not isinstance(a, dict):
                continue
            # ✅ dst/size 슬롯은 value 스캔에서 완전히 건너뜀 (중복 방지의 핵심)
            if i == dst_pos or i == size_pos:
                continue
            for t in self._idents_from_ast_node(a, skip_sizeof=True, skip_callee=True):
                # index/size/base로 이미 집계된 식별자는 value로 중복 집계하지 않음
                if t in index_vars or t in size_vars or t in base_vars:
                    continue
                _emit(t, "value")
            # print( ... )
        return out

    
    

    def _call_write_effects_ast(self, fname: str, arg_nodes: List[Dict[str,Any]]) -> List[str]:
        """
        호출의 '쓰기 효과(DEF)' 대상 식별자를 추출.
        - dst 인자(라이브러리별 위치)에 대해:
        * AddressOf/Paren/Cast 등을 언랩한 실제 대상 기준으로 DEF  # ★
        * MemberAccess -> 'base.field' 풀네임으로 DEF
        * Identifier   -> 이름으로 DEF
        - scanf/fscanf: 포맷 이후 인자들에서 '&x' 패턴은 x를 DEF
        (필드 주소 &s.field 도 지원)
        - 중복 제거 및 KEYWORDS 제외
        """
        defs: List[str] = []

        def _emit(name: str | None):
            if name and name not in KEYWORDS and name not in defs:
                defs.append(name)

        def _first_ident(node: Dict[str, Any] | None) -> str:
            ids = self._idents_from_ast_node(node, skip_sizeof=True, skip_callee=True)
            return ids[0] if ids else ""

        def _dst_fullname(node: Dict[str, Any] | None) -> str:
            """dst가 AddressOf/Paren/Cast 등을 포함해도 실제 대상 기준으로 풀네임/식별자 반환."""
            if not isinstance(node, dict):
                return ""
            # ★ 주소(&), 캐스트, 괄호 언랩
            core = self._unwrap_ast(node, strip_addr=True, strip_cast=True, strip_paren=True) or node  # ★
            full = self._fullname_from_expr(core)  # 'base.field' or ident
            if full:
                return full
            return _first_ident(core)

        def _get_arg(idx: int) -> Dict[str, Any] | None:
            return (arg_nodes or [None])[idx] if 0 <= idx < len(arg_nodes or []) else None

        low = (fname or "").lower()

        # 1) 버퍼/문자열을 '목적지'로 쓰는 호출들: dst 슬롯 DEF                                  
        if low in {"memcpy", "memmove", "strcpy", "strcat", "strncpy",
                "snprintf", "sprintf", "vsnprintf", "vsprintf",
                "fgets", "gets", "memset"}:                                      
            dst_idx = 0
            dst = _get_arg(dst_idx)
            _emit(_dst_fullname(dst))

        elif low in {"recv", "read", "getline"}:
            # recv(int, void* buf, size_t, ...) / read(int, void* buf, size_t)
            # getline(char** lineptr, size_t* n, FILE*): 프로젝트 규칙 상 2번째 인자 DEF
            dst_idx = 1
            dst = _get_arg(dst_idx)
            _emit(_dst_fullname(dst))

        # 2) scanf/fscanf: 포맷 이후 인자들에서 '&x' 주소 전달 → x DEF
        if low in {"scanf", "fscanf"}:
            for a in (arg_nodes or [])[1:]:
                nm = self._extract_address_of_ident(a)
                if nm:
                    _emit(nm)
                    continue
                if isinstance(a, dict) and a.get("nodeType") in {"UnaryOperator", "UnaryExpression"}:
                    kids = a.get("children") or []
                    if kids:
                        full = self._fullname_from_expr(kids[0])  # & (MemberAccess)
                        _emit(full)

        return defs

    def _extract_address_of_ident(self, node: Dict[str,Any] | None) -> str:
        """scanf류 인자의 &v 에서 v 추출 (단순 패턴)"""
        if not isinstance(node, dict):
            return ""
        nt = node.get("nodeType")
        if nt in {"UnaryOperator","UnaryExpression"} and node.get("operator") == "&":
            for ch in node.get("children", []) or []:
                if isinstance(ch, dict) and ch.get("nodeType") == "Identifier":
                    nm = ch.get("name")
                    if isinstance(nm, str):
                        return nm
        # 더 깊은 경우에도 첫 식별자 반환
        ids = self._idents_from_ast_node(node, skip_sizeof=True, skip_callee=True)
        return ids[0] if ids else ""

    # ------------------------------
    # Guard map (AST 조건 서브트리로 분석)
    # ------------------------------
    
    def _lower_from_for_init(self, for_node: Dict[str,Any]) -> Dict[str, Dict[str,Any]]:
        """Detect lower-bound (x >= 0) evidence from ForStatement initializer like x = 0."""
        res: Dict[str, Dict[str,Any]] = {}
        kids = (for_node.get("children") or [])
        init = kids[0] if len(kids) >= 1 else None
        if isinstance(init, dict) and init.get("nodeType") == "AssignmentExpression":
            lhs, rhs = (init.get("children") or [None, None])[:2]
            if isinstance(lhs, dict) and lhs.get("nodeType") == "Identifier" and isinstance(rhs, dict) and rhs.get("nodeType") == "Literal":
                nm = lhs.get("name")
                val = rhs.get("value")
                if isinstance(nm, str) and isinstance(val, str) and val.isdigit():
                    # assume non-negative literal as lower guard
                    if int(val) >= 0:
                        res[nm] = {"lower": 1, "upper": 0, "upper_const": 0.0}
        return res
    
    
    def _build_guard_map(self):
        """
        AST의 guard 에지를 이용해 '변수별 가드(lower/upper/upper_const)'를
        가드 대상 블록의 모든 문장 sid로 전파한 맵을 만든다.

        - If: then(guard_branch==0)만 변수별 가드 적용(else는 역논리 적용하지 않음: 프로젝트 정책)
        - Loop: 조건 변수 가드 적용
        - Switch: 변수 가드 없음(종류(kind)만 전파)
        - 전파 범위: guard 에지의 dst_first(블록 첫 문장)에서 시작해 SB(문장 순서)와 PC(부자관계)를 함께 따라가 블록 내부 전체에 적용
        반환:
            gmap: Dict[int, Dict[str, Dict[str, Any]]]
                각 dst_sid -> {
                    <var>: {"kind":int, "lower":0|1, "upper":0|1, "upper_const":float},
                    "*":   {...},  # 폴백 집계
                    "__agg__": {...}  # "*"와 동일
                }
        """
        from collections import defaultdict, deque

        # ---------- 0) AST 결과/에지 로딩 ----------
        ast_res   = getattr(self, "ast_result", {}) or {}
        pc_edges  = ast_res.get("edges_ast_pc")     or getattr(self, "edges_ast_pc", [])     or []
        sb_edges  = ast_res.get("edges_ast_sb")     or getattr(self, "edges_ast_sb", [])     or []
        grd_edges = ast_res.get("edges_ast_guard")  or getattr(self, "edges_ast_guard", [])  or []

        # ---------- 1) idmap 확보 (없으면 AST에서 직접 구성) ----------
        def _build_idmap_from_ast(root):
            m = {}
            def walk(n):
                if isinstance(n, dict):
                    nid = n.get("id")
                    if isinstance(nid, int):
                        m[nid] = n
                    for c in n.get("children") or []:
                        walk(c)
                elif isinstance(n, list):
                    for c in n:
                        walk(c)
            walk(root)
            return m

        idmap = getattr(self, "idmap", None)
        if not isinstance(idmap, dict) or not idmap:
            # 후보: self.ast_json, ast_result["ast_json"], self.ast, ast_result["ast"]
            ast_root = getattr(self, "ast_json", None) \
                    or ast_res.get("ast_json") \
                    or getattr(self, "ast", None) \
                    or ast_res.get("ast")
            if isinstance(ast_root, dict):
                idmap = _build_idmap_from_ast(ast_root)
                # 다음 호출에서도 쓰이도록 캐싱(있으면 덮어써도 무해)
                try:
                    self.idmap = idmap
                except Exception:
                    pass
            else:
                idmap = {}

        # ---------- 2) sid → (node_type, orig_ast_node) 조회 헬퍼 ----------
        # 2-1) sid→orig_id를 얻는 여러 폴백 경로
        sid2flat = getattr(self, "sid2flat", None)
        ast_nodes_list = ast_res.get("nodes") or []

        def _orig_ast_for_sid(sid: int):
            # (a) sid2flat 경유
            if isinstance(sid2flat, dict):
                row = sid2flat.get(sid) or {}
                oid = row.get("orig_id")
                if isinstance(oid, int):
                    return idmap.get(oid)
            # (b) ast_result["nodes"] 선형 탐색
            for r in ast_nodes_list:
                try:
                    if int(r.get("sid")) == sid:
                        oid = r.get("orig_id")
                        if isinstance(oid, int):
                            return idmap.get(oid)
                except Exception:
                    continue
            # (c) self.nodes 안에 orig_id가 직접 들어있는 경우
            for r in (self.nodes or []):
                try:
                    if int(r.get("sid")) == sid:
                        oid = r.get("orig_id")
                        if isinstance(oid, int):
                            return idmap.get(oid)
                except Exception:
                    continue
            return None

        # 2-2) sid → node_type_id(또는 node_type)
        sid2type = {}
        for r in (self.nodes or []):
            sid2type[r.get("sid")] = r.get("node_type_id") or r.get("node_type")

        # ---------- 3) 인접리스트 구성 ----------
        pc = defaultdict(list)
        for e in pc_edges:
            if isinstance(e, (list, tuple)) and len(e) >= 2:
                try:
                    src, dst = int(e[0]), int(e[1])
                except Exception:
                    continue
            elif isinstance(e, dict):
                try:
                    src, dst = int(e.get("src")), int(e.get("dst"))
                except Exception:
                    continue
            else:
                continue
            pc[src].append(dst)

        sb = defaultdict(list)
        for e in sb_edges:
            if isinstance(e, (list, tuple)) and len(e) >= 2:
                try:
                    src, dst = int(e[0]), int(e[1])
                except Exception:
                    continue
            elif isinstance(e, dict):
                try:
                    src, dst = int(e.get("src")), int(e.get("dst"))
                except Exception:
                    continue
            else:
                continue
            sb[src].append(dst)

        # ---------- 4) 제어문 조건 가드 해석 ----------
        CONTROL = {"IfStatement", "ForStatement", "WhileStatement", "DoWhileStatement", "DoStatement"}

        # _get_condition_node 없을 때를 대비한 안전 폴백
        def _get_cond_ast_fallback(nt: str, ast_node: dict):
            kids = (ast_node.get("children") or []) if isinstance(ast_node, dict) else []
            if nt == "IfStatement":
                return kids[0] if len(kids) >= 1 and isinstance(kids[0], dict) else None
            if nt == "ForStatement":
                return kids[1] if len(kids) >= 2 and isinstance(kids[1], dict) else None
            if nt == "WhileStatement":
                return kids[0] if len(kids) >= 1 and isinstance(kids[0], dict) else None
            if nt in {"DoWhileStatement", "DoStatement"}:
                # 마지막 비-CompoundStatement를 조건으로 추정
                for k in reversed(kids):
                    if isinstance(k, dict) and k.get("nodeType") != "CompoundStatement":
                        return k
                return None
            return None

        cond_guard_by_src = {}  # src_sid -> { var: {lower, upper, upper_const} }
        for sid, nt in sid2type.items():
            if nt not in CONTROL:
                continue
            ast_node = _orig_ast_for_sid(sid)
            if not isinstance(ast_node, dict):
                continue
            # 조건 AST 획득
            try:
                cond_ast = self._get_condition_node(nt, ast_node)
            except Exception:
                cond_ast = _get_cond_ast_fallback(nt, ast_node)

            parsed = {}
            if cond_ast is not None:
                try:
                    parsed = self._guards_from_condition_ast(cond_ast) or {}
                except Exception:
                    parsed = {}

            # 정규화
            norm = {}
            for v, g in (parsed.items() if isinstance(parsed, dict) else []):
                if not v:
                    continue
                try:
                    norm[v] = {
                        "lower": int(g.get("lower", 0)),
                        "upper": int(g.get("upper", 0)),
                        "upper_const": float(g.get("upper_const", 0.0)),
                    }
                except Exception:
                    norm[v] = {"lower": 0, "upper": 0, "upper_const": 0.0}
        
        
            # 🔸 ForStatement: 헤더(init/inc)에서 하한 보강
            if nt == "ForStatement":
                extra = self._guards_from_for_header(ast_node) or {}
                for v, g in extra.items():
                    e = norm.setdefault(v, {"lower":0,"upper":0,"upper_const":0.0})
                    e["lower"] = max(e["lower"], int(g.get("lower", 0)))
                    # upper/upper_const는 조건식 쪽 결과 유지

        
            cond_guard_by_src[sid] = norm

        # ---------- 5) guard 에지 따라 블록 범위로 전파 ----------
        gmap = defaultdict(dict)  # dst_sid -> { var: {...}, "*": {...}, "__agg__": {...} }

        def _merge_agg(dst_cur: dict, add: dict, kind: int):
            cur = dst_cur or {"kind": kind, "lower": 0, "upper": 0, "upper_const": 0.0}
            cur["kind"] = cur.get("kind", 0) or kind
            try:
                cur["lower"] = max(int(cur.get("lower", 0)), int(add.get("lower", 0)))
                cur["upper"] = max(int(cur.get("upper", 0)), int(add.get("upper", 0)))
                cur["upper_const"] = max(float(cur.get("upper_const", 0.0)), float(add.get("upper_const", 0.0)))
            except Exception:
                pass
            return cur

        for ge in grd_edges:
            # dict 포맷: {"src","dst","edge_type":2,"guard_kind":1|2|4,"guard_branch":...}
            if isinstance(ge, dict):
                try:
                    src_sid   = int(ge.get("src", -1))
                    dst_first = int(ge.get("dst", -1))
                    kind      = int(ge.get("guard_kind", 0))
                except Exception:
                    continue
                branch = ge.get("guard_branch", None)
            # list/tuple 포맷(예외): [src, dst, {"feat":{"guard_kind":...}, ...}]
            elif isinstance(ge, (list, tuple)) and len(ge) >= 3 and isinstance(ge[2], dict):
                try:
                    src_sid   = int(ge[0]); dst_first = int(ge[1])
                except Exception:
                    continue
                feat = ge[2].get("feat", {}) if isinstance(ge[2], dict) else {}
                kind = int((feat.get("guard_kind") if isinstance(feat, dict) else 0) or 0)
                branch = None
            else:
                continue

            if kind not in (1, 2, 4):
                continue

            # 변수별 가드 선택
            var_g = {}
            if kind == 1:   # If
                if branch == 0:  # then
                    var_g = cond_guard_by_src.get(src_sid, {}) or {}
                else:
                    var_g = {}
            elif kind == 2: # Loop
                var_g = cond_guard_by_src.get(src_sid, {}) or {}
            else:           # Switch
                var_g = {}

            # 집계 가드
            agg = {"kind": kind, "lower": 0, "upper": 0, "upper_const": 0.0}
            for g in var_g.values():
                try:
                    agg["lower"] |= int(g.get("lower", 0))
                    agg["upper"] |= int(g.get("upper", 0))
                    uc = float(g.get("upper_const", 0.0))
                    if uc > agg["upper_const"]:
                        agg["upper_const"] = uc
                except Exception:
                    pass

            # dst_first에서 시작해 SB + PC를 같이 따라가며 전파
            q = deque([dst_first]); seen = set()
            while q:
                u = q.popleft()
                if u in seen:
                    continue
                seen.add(u)

                entry = gmap.setdefault(u, {})

                # 변수별 병합
                for v, g in var_g.items():
                    cur = entry.get(v, {"kind": kind, "lower": 0, "upper": 0, "upper_const": 0.0})
                    if not cur.get("kind"):
                        cur["kind"] = kind
                    try:
                        cur["lower"] |= int(g.get("lower", 0))
                        cur["upper"] |= int(g.get("upper", 0))
                        cur["upper_const"] = max(float(cur.get("upper_const", 0.0)),
                                                float(g.get("upper_const", 0.0)))
                    except Exception:
                        pass
                    entry[v] = cur

                # 폴백("*", "__agg__")
                entry["*"] = _merge_agg(entry.get("*"), agg, kind)
                entry["__agg__"] = entry["*"]

                # 확장
                for v in sb.get(u, []):
                    if v not in seen:
                        q.append(v)
                for v in pc.get(u, []):
                    if v not in seen:
                        q.append(v)

        return gmap


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
            if n.get("nodeType") in {"Literal","IntegerLiteral","NumberLiteral"}:
                t = (n.get("type") or "").lower()
                return "int" in t or t == ""  # 일부 파서에서 type 비울 수 있음
            return False

        def _int_from_node(n: dict) -> int | None:
            # Literal("10"), 혹은 Unary - Literal("10")
            if not isinstance(n, dict):
                return None
            if _is_int_literal(n):
                v = n.get("value")
                try:
                    return int(str(v).strip())
                except Exception:
                    # fallback: 코드에서 추출
                    code = n.get("code","")
                    import re
                    m = re.search(r'-?\d+', code)
                    return int(m.group(0)) if m else None
            # Unary - <literal>
            if n.get("nodeType") in {"UnaryOperator","UnaryExpression"} and n.get("operator") == "-":
                kids = n.get("children") or []
                k0 = kids[0] if kids else None
                val = _int_from_node(k0)
                return -val if isinstance(val, int) else None
            # 괄호로 감싼 케이스 (ParenthesizedExpression 류)
            if n.get("nodeType") in {"ParenExpression","ParenthesizedExpression"}:
                ks = n.get("children") or []
                return _int_from_node(ks[0]) if ks else None
            return None

        def _ident_name(n: dict) -> str | None:
            if not isinstance(n, dict):
                return None
            nt = n.get("nodeType")
            if nt == "Identifier":
                nm = n.get("name")
                return nm if isinstance(nm, str) and nm else None
            if nt == "MemberAccess":
                kids = n.get("children") or []
                base = kids[0] if len(kids) > 0 else None
                field= kids[1] if len(kids) > 1 else None
                b = _ident_name(base)
                f = _ident_name(field)
                if b and f:
                    return f"{b}.{f}"
                return b or f
            # 괄호/캐스트로 감싼 경우 풀어주기
            if nt in {"ParenExpression","ParenthesizedExpression","CStyleCastExpression","CXXStaticCastExpr","UnaryOperator","UnaryExpression"}:
                kids = n.get("children") or []
                return _ident_name(kids[0]) if kids else None
            return None

        def _emit_lower(var: str):
            if not var:
                return
            e = out.setdefault(var, {"lower":0,"upper":0,"upper_const":0.0})
            e["lower"] = 1

        def _emit_upper(var: str, k: int | None):
            if not var:
                return
            e = out.setdefault(var, {"lower":0,"upper":0,"upper_const":0.0})
            e["upper"] = 1
            if isinstance(k, int):
                e["upper_const"] = max(e["upper_const"], _norm_val(k))  # 최대값 유지

        # ---------- recursive visit ----------
        def visit(n: dict):
            if not isinstance(n, dict):
                return
            nt = n.get("nodeType")
            if nt == "BinaryExpression":
                op = n.get("operator")
                ch = n.get("children") or []
                a = ch[0] if len(ch) > 0 else None
                b = ch[1] if len(ch) > 1 else None

                # 논리연산: && / ||
                if op in {"&&","and","AND"}:
                    visit(a); visit(b); return
                if op in {"||","or","OR"}:
                    # 보수적으로 두 쪽 모두 반영(합집합)
                    visit(a); visit(b); return

                # 비교연산
                if op in {"<","<=",">",">="}:
                    # 케이스 1) var ? const
                    v_left  = _ident_name(a)
                    k_right = _int_from_node(b)

                    # 케이스 2) const ? var  (좌우 뒤집힘)
                    k_left  = _int_from_node(a)
                    v_right = _ident_name(b)

                    if v_left:
                        if op in {">",">="}:
                            # x > 0, x >= 0 → lower
                            if (k_right is not None) and k_right == 0:
                                _emit_lower(v_left)
                        elif op in {"<","<="}:
                            # x < K, x <= K → upper(+const)
                            _emit_upper(v_left, k_right)
                        return

                    if v_right:
                        # 뒤집힌 비교는 연산자 방향 반대로 해석
                        if op in {">",">="}:
                            # K > x ⇒ x < K
                            _emit_upper(v_right, k_left)
                        elif op in {"<","<="}:
                            # K < x ⇒ x > K  (K가 0일 때만 lower 인정; 일반 K는 무시)
                            if (k_left is not None) and k_left == 0:
                                _emit_lower(v_right)
                        return

                    # 둘 다 변수/상수 아니면 스킵
                    return

            # 괄호/캐스트/단항은 내부로
            if nt in {"ParenExpression","ParenthesizedExpression","CStyleCastExpression","CXXStaticCastExpr",
                    "UnaryOperator","UnaryExpression"}:
                for c in (n.get("children") or []):
                    visit(c)
                return

            # 논리식이 다른 노드(예: ConditionalOperator 등)면 하위 탐색
            for c in (n.get("children") or []):
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
            if not v: return
            e = out.setdefault(v, {"lower":0,"upper":0,"upper_const":0.0})
            e["lower"] = 1

        if not isinstance(for_ast, dict) or for_ast.get("nodeType") != "ForStatement":
            return out

        kids = (for_ast.get("children") or [])
        init = kids[0] if len(kids) >= 1 else None
        inc  = kids[2] if len(kids) >= 3 else None

        # helper: 정수리터럴 추출
        def _int_from(n):
            if not isinstance(n, dict): return None
            if n.get("nodeType") in {"Literal","IntegerLiteral","NumberLiteral"}:
                try: return int(str(n.get("value")).strip())
                except: return None
            if n.get("nodeType") in {"UnaryOperator","UnaryExpression"} and n.get("operator") == "-":
                ks = n.get("children") or []
                v = _int_from(ks[0]) if ks else None
                return -v if isinstance(v, int) else None
            if n.get("nodeType") in {"ParenExpression","ParenthesizedExpression"}:
                ks = n.get("children") or []
                return _int_from(ks[0]) if ks else None
            return None

        # helper: 식별자 이름 추출 (Identifier/MemberAccess)
        def _ident(n):
            if not isinstance(n, dict): return None
            nt = n.get("nodeType")
            if nt == "Identifier":
                nm = n.get("name"); return nm if isinstance(nm,str) and nm else None
            if nt == "MemberAccess":
                ks = n.get("children") or []
                b = _ident(ks[0] if len(ks)>0 else None)
                f = _ident(ks[1] if len(ks)>1 else None)
                return f"{b}.{f}" if b and f else (b or f)
            if nt in {"ParenExpression","ParenthesizedExpression","CStyleCastExpression","CXXStaticCastExpr",
                    "UnaryOperator","UnaryExpression"}:
                ks = n.get("children") or []
                return _ident(ks[0]) if ks else None
            return None

        # 1) init: i = K (K>=0)
        init_var = None
        init_nonneg = False
        if isinstance(init, dict) and init.get("nodeType") == "AssignmentExpression" and init.get("operator") == "=":
            ch = init.get("children") or []
            lhs, rhs = (ch[0] if len(ch)>0 else None), (ch[1] if len(ch)>1 else None)
            init_var = _ident(lhs)
            kv = _int_from(rhs)
            init_nonneg = isinstance(kv, int) and kv >= 0

        # 2) inc: ++i / i++ / i += k (k>=0)
        inc_var = None
        inc_nondecreasing = False
        if isinstance(inc, dict):
            nt = inc.get("nodeType")
            if nt in {"UnaryOperator","UnaryExpression"} and inc.get("operator") in {"++"}:
                ks = inc.get("children") or []
                inc_var = _ident(ks[0]) if ks else None
                inc_nondecreasing = True
            elif nt == "AssignmentExpression" and inc.get("operator") in {"+="}:
                ch = inc.get("children") or []
                lhs, rhs = (ch[0] if len(ch)>0 else None), (ch[1] if len(ch)>1 else None)
                inc_var = _ident(lhs)
                step = _int_from(rhs)
                inc_nondecreasing = isinstance(step, int) and step >= 0

        # 3) 결론: init와 inc가 같은 변수이고 init_nonneg & inc_nondecreasing면 lower=1
        if init_var and inc_var and init_var == inc_var and init_nonneg and inc_nondecreasing:
            _emit_lower(init_var)

        return out
    

    def _guard_ctx_by_sid(self, sid: int) -> dict:
        f = self._sid2feat.get(int(sid), {}) or {}
        # kind: 루프 안이면 2(while/for), 아니면 if(1) 또는 없음(0)
        kind = 2 if f.get("in_loop", 0) else (1 if f.get("ctx_guard_strength", 0) else 0)
        s = int(f.get("ctx_guard_strength", 0) or 0)  # 0:none, 1:lower, 2:upper, 3:both
        return {
            "kind": kind,
            "lower": 1 if s in (1, 3) else 0,
            "upper": 1 if s in (2, 3) else 0,
            "upper_const": float(f.get("ctx_upper_bound_norm", 0.0) or 0.0),
        }
    def _find_first_call_node(self, node):
        def walk(n):
            if not isinstance(n, dict): return None
            if n.get("nodeType") in {"StandardLibCall","UserDefinedCall","CallExpression"}:
                return n
            for ch in (n.get("children") or []):
                r = walk(ch)
                if r is not None: return r
            return None
        return walk(node)

    def _sb_has(self, prev_sid:int, next_sid:int)->bool:
        try: return (int(prev_sid), int(next_sid)) in self.sb_edges
        except Exception: return False
    
    def _unwrap_ast(self, node: dict | None,
                    strip_addr: bool = False,
                    strip_cast: bool = True,
                    strip_paren: bool = True) -> dict | None:
            """AST 표현식에서 바깥 래핑을 옵션대로 벗겨 내부 '핵심' 표현식을 반환."""
            n = node
            while isinstance(n, dict):
                nt = n.get("nodeType")

                # 우리 AST 스키마에서는 이런 타입이 없음
                #if strip_paren and nt in {"ParenExpression","ParenExpr"}:
                #    kids = [c for c in (n.get("children") or []) if isinstance(c, dict)]
                #    n = kids[0] if kids else None
                #    continue

                if strip_cast and nt in {"CastExpression","CStyleCastExpr"}:
                    kids = [c for c in (n.get("children") or []) if isinstance(c, dict)]
                    n = next((c for c in kids
                            if c.get("nodeType") not in {"TypeRef","TypeName","TypeSpecifier"}), None)
                    continue

                if strip_addr and (nt == "AddressOfExpression" or
                                (nt == "UnaryOperator" and n.get("operator") in {"&","&amp;"})):
                    kids = [c for c in (n.get("children") or []) if isinstance(c, dict)]
                    n = kids[0] if kids else None
                    continue
                break
            return n
