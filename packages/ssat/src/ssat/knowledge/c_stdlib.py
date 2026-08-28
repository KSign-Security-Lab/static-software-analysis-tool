"""C standard-library facts shared by the analysis stages.

Single source of truth for "what does this libc call do to memory". Before this
module the same tables were restated in ``ast/extractor.py``, ``dfg/extractor.py``
and ``template/config/standard_lib_call.py``, and drifted between them.

Scope note: F2-A keeps its own knowledge base (``ssat.f2a.kb``). That one encodes
OCPP protocol semantics and check patterns, which is a different question from
libc memory behaviour -- the two are deliberately not merged.
"""

from typing import Dict

# 1) Fixed IDs
CALL_SEM_ID = {
    "none": 0,
    "mem_alloc": 1,
    "mem_copy": 2,
    "ext_input": 3,
    "format_print": 4,
    "mem_set": 5,
    "net_connect": 6,
    "net_close": 7,
    "socket_create": 8,
    "parse_int_unchecked": 9,
    "parse_int_checked": 10,
}

# Priority: mem_copy > ext_input > mem_alloc > format_print > none
CALL_PRIORITY = [
    "none",
    "mem_alloc",
    "mem_copy",
    "ext_input",
    "format_print",
    "mem_set",
    "net_connect",
    "net_close",
    "socket_create",
    "parse_int_unchecked",
    "parse_int_checked",  # id 9, 10
]


# --- 3) Category definitions (human-readable dict-of-sets) ---
CALL_SEM = {
    # Memory allocation (heap/stack combined)
    "mem_alloc": {
        # heap-like
        "malloc",
        "calloc",
        "realloc",
        "xmalloc",
        "xcalloc",
        "xrealloc",
        "valloc",
        "memalign",
        "HeapAlloc",
        "HeapReAlloc",
        "HeapCreate",
        "new",
        "new[]",
        # stack-like
        "alloca",
        "ALLOCA",
        "_alloca",
    },
    # Memory/string copy/concat (sink)
    "mem_copy": {
        # raw memory
        "memcpy",
        "memmove",
        "memcpy_s",
        "memmove_s",
        "bcopy",
        "CopyMemory",
        "RtlCopyMemory",
        "wmemcpy",
        "wmemmove",
        "wmemcpy_s",
        "wmemmove_s",
        # string copy
        "strcpy",
        "strcpy_s",
        "strncpy",
        "strncpy_s",
        "wcscpy",
        "wcscpy_s",
        "wcsncpy",
        "wcsncpy_s",
        "lstrcpy",
        "lstrcpyn",
        "StrCpy",
        "StrCpyN",
        "StrCpyNW",
        # string concat
        "strcat",
        "strcat_s",
        "strncat",
        "strncat_s",
        "wcscat",
        "wcscat_s",
        "wcsncat",
        "wcsncat_s",
        "lstrcat",
        "StrCat",
        "StrCatN",
        "StrCatNW",
    },
    # External input (source)
    "ext_input": {
        "gets",
        "gets_s",
        "fgets",
        "getline",
        "scanf",
        "sscanf",
        "fscanf",
        "scanf_s",
        "sscanf_s",
        "fscanf_s",
        "wscanf",
        "swscanf",
        "fwscanf",
        "wscanf_s",
        "swscanf_s",
        "fwscanf_s",
        "read",
        "pread",
        "pread64",
        "fread",
        "recv",
        "recvfrom",
    },
    # Format output (string generation sink)
    "format_print": {
        "printf",
        "fprintf",
        "vprintf",
        "vfprintf",
        "puts",
        "printIntLine",
        "sprintf",
        "vsprintf",
        "snprintf",
        "vsnprintf",
        "sprintf_s",
        "vsprintf_s",
        # Windows/MSVC family included
        "_snprintf",
        "_vsnprintf",
        "_snwprintf",
        "_vsntprintf",
        "swprintf",
        "vswprintf",
        "vswprintf_s",
        "wsprintf",
        "wvsprintf",
        "wnsprintf",
        "wvnsprintf",
    },
    # Others
    "mem_set": {"memset", "bzero", "wmemset", "RtlZeroMemory"},
    "net_connect": {"connect"},
    "net_close": {"closesocket", "close", "close_socket", "CLOSE_SOCKET"},
    "socket_create": {"socket", "WSASocket", "wsasocket"},
    "parse_int_unchecked": {"atoi", "atol", "atoll", "_atoi64"},
    "parse_int_checked": {
        "strtol",
        "strtoul",
        "strtoll",
        "strtoull",
        "strtoimax",
        "strtoumax",
        "wcstol",
        "wcstoul",
        "wcstoll",
        "wcstoull",
        "wcstoimax",
        "wcstoumax",
    },
}


# 4) Build flat map: reflect priority + IDs from fixed table
CALL_SEM_MAP: Dict[str, int] = {}
for cat in CALL_PRIORITY:
    cid = CALL_SEM_ID[cat]
    for nm in CALL_SEM.get(cat, ()):
        CALL_SEM_MAP.setdefault(nm.lower(), cid)  # preserve first encountered (higher priority) mapping


def call_sem_cat_id_from_name(name: str) -> int:
    """Semantic-category id for a call name, or 0 when unknown."""
    return int(CALL_SEM_MAP.get((name or "").lower(), 0))


# Unbounded risks (no length arg / format specifier width needed)
UNBOUNDED_CALLS = {
    # Existing
    "gets",
    "strcpy",
    "strcat",
    "sprintf",
    "vsprintf",
    # Input (unbounded) - wide/MSVC
    "_getws",  # wide version of gets
    "getwd",  # writes path to buffer without size arg (Not recommended)
    # String copy/concat (no size arg)
    "wcscpy",
    "wcscat",  # wide
    "lstrcpy",
    "lstrcat",  # Win32
    "stpcpy",
    "wcpcpy",  # GNU extension (returns end pointer)
    "_mbscpy",
    "_mbscat",  # Multibyte (MBCS)
    # Format output (no size arg)
    "wsprintf",
    "wvsprintf",  # Win32 (sprintf의 wide/va 버전)
}

# dst/size slots (simple) - for AST flag calculation
API_SLOTS = {
    # --- mem_set / copy ---
    # void *memset(void *dst, int c, size_t size)
    "memset": {"dst": 0, "size": 2},
    # void bzero(void *dst, size_t size)
    "bzero": {"dst": 0, "size": 1},
    # wchar_t *wmemset(wchar_t *dst, wchar_t c, size_t n)
    "wmemset": {"dst": 0, "size": 2},
    # void RtlZeroMemory(void *dst, size_t size)
    "rtlzeromemory": {"dst": 0, "size": 1},
    # void *memcpy(void *dst, const void *src, size_t size)
    "memcpy": {"dst": 0, "size": 2},
    # errno_t memcpy_s(void *dst, rsize_t dstsz, const void *src, rsize_t count)
    "memcpy_s": {"dst": 0, "size": 3},  # count
    # void *memmove(void *dst, const void *src, size_t size)
    "memmove": {"dst": 0, "size": 2},
    # errno_t memmove_s(void *dst, rsize_t dstsz, const void *src, rsize_t count)
    "memmove_s": {"dst": 0, "size": 3},  # count
    # void bcopy(const void *src, void *dst, size_t size)
    "bcopy": {"dst": 1, "size": 2},
    # VOID CopyMemory(PVOID dst, const VOID *src, SIZE_T size)
    "copymemory": {"dst": 0, "size": 2},
    # VOID RtlCopyMemory(VOID *dst, const VOID *src, SIZE_T size)
    "rtlcopymemory": {"dst": 0, "size": 2},
    # wide raw memory copy
    "wmemcpy": {"dst": 0, "size": 2},
    "wmemcpy_s": {"dst": 0, "size": 3},  # count
    "wmemmove": {"dst": 0, "size": 2},
    "wmemmove_s": {"dst": 0, "size": 3},  # count
    # string copy/concat (unbounded/has size)
    # char *strcpy(char *dst, const char *src)
    "strcpy": {"dst": 0, "size": None},
    # errno_t strcpy_s(char *dst, rsize_t dstsz, const char *src)
    "strcpy_s": {"dst": 0, "size": 1},  # dstsz
    # char *strncpy(char *dst, const char *src, size_t n)
    "strncpy": {"dst": 0, "size": 2},
    # errno_t strncpy_s(char *dst, rsize_t dstsz, const char *src, rsize_t n)
    "strncpy_s": {"dst": 0, "size": 3},  # n
    # wide string copy
    "wcscpy": {"dst": 0, "size": None},
    "wcscpy_s": {"dst": 0, "size": 1},  # dstsz
    "wcsncpy": {"dst": 0, "size": 2},
    "wcsncpy_s": {"dst": 0, "size": 3},  # n
    # win32 string copy variants
    # LPTSTR lstrcpy(LPTSTR dst, LPCTSTR src)
    "lstrcpy": {"dst": 0, "size": None},
    # int lstrcpyn(LPTSTR dst, LPCTSTR src, int cchMax)
    "lstrcpyn": {"dst": 0, "size": 2},
    # StrCpyX family (plain "strcpy" is already listed above; lower() maps "StrCpy" onto it)
    "strcpyn": {"dst": 0, "size": 2},  # StrCpyN
    "strcpynw": {"dst": 0, "size": 2},  # StrCpyNW
    # char *strcat(char *dst, const char *src)
    "strcat": {"dst": 0, "size": None},
    # errno_t strcat_s(char *dst, rsize_t dstsz, const char *src)
    "strcat_s": {"dst": 0, "size": 1},  # dstsz
    # char *strncat(char *dst, const char *src, size_t n)
    "strncat": {"dst": 0, "size": 2},
    # errno_t strncat_s(char *dst, rsize_t dstsz, const char *src, rsize_t n)
    "strncat_s": {"dst": 0, "size": 3},  # n
    # wide string concat
    "wcscat": {"dst": 0, "size": None},
    "wcscat_s": {"dst": 0, "size": 1},  # dstsz
    "wcsncat": {"dst": 0, "size": 2},
    "wcsncat_s": {"dst": 0, "size": 3},  # n
    # win32 string concat variants
    "lstrcat": {"dst": 0, "size": None},
    "strcatn": {"dst": 0, "size": 2},  # StrCatN(dst, src, count)
    "strcatnw": {"dst": 0, "size": 2},  # StrCatNW(dst, src, count)
    # --- ext_input ---
    # gets 계열
    "gets": {"dst": 0, "size": None},  # Dangerous: unlimited
    "gets_s": {"dst": 0, "size": 1},  # numberOfElements
    # fgets / getline
    "fgets": {"dst": 0, "size": 1},  # size
    "getline": {"dst": None, "size": None},  # dynamic return -> no dst/size linkage
    # scanf family (format parsing needed -> size position undefined)
    "scanf": {"dst": None, "size": None},
    "sscanf": {"dst": None, "size": None},
    "fscanf": {"dst": None, "size": None},
    "scanf_s": {"dst": None, "size": None},
    "sscanf_s": {"dst": None, "size": None},
    "fscanf_s": {"dst": None, "size": None},
    "wscanf": {"dst": None, "size": None},
    "swscanf": {"dst": None, "size": None},
    "fwscanf": {"dst": None, "size": None},
    "wscanf_s": {"dst": None, "size": None},
    "swscanf_s": {"dst": None, "size": None},
    "fwscanf_s": {"dst": None, "size": None},
    # read 계열
    # ssize_t read(int fd, void *buf, size_t count)
    "read": {"dst": 1, "size": 2},
    # ssize_t pread(int fd, void *buf, size_t count, off_t offset)
    "pread": {"dst": 1, "size": 2},
    # ssize_t pread64(int fd, void *buf, size_t count, off64_t offset)
    "pread64": {"dst": 1, "size": 2},
    # size_t fread(void *ptr, size_t size, size_t nmemb, FILE *stream)
    # (Total bytes are size*nmemb, but size=1 is often used by convention in single-slot models.
    # Maintain size=2 for compatibility or enhance logic if needed.)
    "fread": {"dst": 0, "size": 2},
    # recv 계열
    # int recv(SOCKET s, char *buf, int len, int flags)
    "recv": {"dst": 1, "size": 2},
    # int recvfrom(SOCKET s, char *buf, int len, int flags, ... )
    "recvfrom": {"dst": 1, "size": 2},
    # --- format_print ---
    # int sprintf(char *dst, const char *fmt, ...)
    "sprintf": {"dst": 0, "size": None},  # unlimited
    "vsprintf": {"dst": 0, "size": None},  # unlimited
    # int snprintf(char *dst, size_t size, const char *fmt, ...)
    "snprintf": {"dst": 0, "size": 1},
    "vsnprintf": {"dst": 0, "size": 1},
    # msvc
    "_snprintf": {"dst": 0, "size": 1},
    "_vsnprintf": {"dst": 0, "size": 1},
    "_snwprintf": {"dst": 0, "size": 1},
    "_vsntprintf": {"dst": 0, "size": 1},
    # wide
    # swprintf exists as (dst,size,fmt,...) or (dst,fmt,...) depending on implementation/overload.
    # Cannot branch in a single table -> only most common safe type included.
    "swprintf": {"dst": 0, "size": 1},  # supported variant with size arg
    "vswprintf": {"dst": 0, "size": 1},  # supported variant with size arg
    "vswprintf_s": {"dst": 0, "size": 1},  # MSVC secure
    # wsprintf/ wvsprintf have no size arg (unbounded)
    "wsprintf": {"dst": 0, "size": None},
    "wvsprintf": {"dst": 0, "size": None},
    # wnsprintf / wvnsprintf have size arg
    "wnsprintf": {"dst": 0, "size": 1},
    "wvnsprintf": {"dst": 0, "size": 1},
    # --- net / others ---
    # int connect(SOCKET s, const struct sockaddr *name, int namelen)
    "connect": {"dst": 1, "size": 2},  # addr / addrlen (memory dst meaning is weak)
    # socket/close/create types have no len concept -> None
    "closesocket": {"dst": None, "size": None},
    "close": {"dst": None, "size": None},
    "close_socket": {"dst": None, "size": None},
    "socket": {"dst": None, "size": None},
    "wsasocket": {"dst": None, "size": None},
    # parse_int family also has no size concept
    "atoi": {"dst": None, "size": None},
    "atol": {"dst": None, "size": None},
    "atoll": {"dst": None, "size": None},
    "_atoi64": {"dst": None, "size": None},
    "strtol": {"dst": None, "size": None},
    "strtoul": {"dst": None, "size": None},
    "strtoll": {"dst": None, "size": None},
    "strtoull": {"dst": None, "size": None},
    "strtoimax": {"dst": None, "size": None},
    "strtoumax": {"dst": None, "size": None},
    "wcstol": {"dst": None, "size": None},
    "wcstoul": {"dst": None, "size": None},
    "wcstoll": {"dst": None, "size": None},
    "wcstoull": {"dst": None, "size": None},
    "wcstoimax": {"dst": None, "size": None},
    "wcstoumax": {"dst": None, "size": None},
}
# Integration points for compute_call_flags
# call_flag_danger_unbounded = 1 if name in UNBOUNDED_CALLS
# call_size_kind, call_len_linked_to_dst_extended, call_flag_sizeof_non_dst are calculated based on API_SLOTS[name]["size"] arg
# call_dst_is_field = 1 if dst is s.field/p->field
# format_print family sets call_flag_has_varargs appropriately (especially v* family)


# ---- mem-alloc helpers ----
MEM_ALLOC_FUNCS_LOWER = {"malloc", "calloc", "realloc", "alloca", "_alloca"}
MEM_ALLOC_FUNCS_RAW = {"ALLOCA", "new[]"}  # preserve case tokens


# Unbounded write family
UNBOUNDED = {"gets", "strcpy", "strcat", "sprintf", "vsprintf"}
# Standard library call detection (simple): based on union of CALL_SEM and UNBOUNDED
STD_FUNCTIONS = set().union(*CALL_SEM.values(), UNBOUNDED)


# Bounded write family: takes an explicit length argument. Complement of
# UNBOUNDED for sink classification in the def-use DFG.
BOUNDED = {
    "memcpy",
    "memmove",
    "strncpy",
    "snprintf",
    "vsnprintf",
    "fgets",
    "read",
    "recv",
    "getline",
}


# Which argument is the destination buffer and which is the size, for the
# UNBOUNDED/BOUNDED families the def-use DFG classifies as sinks. This lived
# inline in ``DFGExtractor.run()``.
#
# Deliberately *not* merged into API_SLOTS above, which is broader (97 entries)
# but disagrees on two of these:
#
#   connect  API_SLOTS says dst=1, but arg 1 is ``const struct sockaddr *addr``
#            -- an input the call reads, not a buffer it writes. The DFG wants
#            no destination here.
#   getline  absent from API_SLOTS; the DFG needs dst=0 (``lineptr``) and
#            size=1 (``n``).
#
# Reconciling the two tables would change what the DFG reports, so they are kept
# apart until someone decides which is right for each caller.
DFG_SINK_SLOTS: Dict[str, Dict[str, int | None]] = {
    "fgets": {"dst": 0, "size": 1},
    "gets": {"dst": 0, "size": None},
    "memcpy": {"dst": 0, "size": 2},
    "memmove": {"dst": 0, "size": 2},
    "strncpy": {"dst": 0, "size": 2},
    "snprintf": {"dst": 0, "size": 1},
    "vsnprintf": {"dst": 0, "size": 1},
    "strcpy": {"dst": 0, "size": None},
    "strcat": {"dst": 0, "size": None},
    "sprintf": {"dst": 0, "size": None},
    "vsprintf": {"dst": 0, "size": None},
    "read": {"dst": 1, "size": 2},
    "recv": {"dst": 1, "size": 2},
    "getline": {"dst": 0, "size": 1},
    "memset": {"dst": 0, "size": 2},
    "connect": {"dst": None, "size": 2},
}


def dfg_sink_slots(name: str) -> Dict[str, int | None]:
    """Destination/size argument positions for ``name``, empty if it is not a known sink."""
    return DFG_SINK_SLOTS.get(name, {})


# The *third* destination/size table, this one for the AST pass's call flags.
#
# All three agree on memcpy, memmove, strncpy, memset, snprintf, vsnprintf,
# fgets, read and recv. They differ on:
#
#   connect   here dst=1, as in API_SLOTS; DFG_SINK_SLOTS says None, reading
#             arg 1 as an address the call consumes rather than a buffer it fills.
#   getline   absent here and from API_SLOTS; present in DFG_SINK_SLOTS.
#   the       unbounded family (gets, strcpy, strcat, sprintf, vsprintf) is
#   absent    absent here, so it gets no slots and therefore no size flags --
#             which is consistent, since none of them takes a size argument.
#
# Each entry also declares how many arguments the call must have before the slots
# mean anything; below that the AST pass reads no slots at all.
AST_FLAG_SLOTS: Dict[str, Dict[str, int]] = {
    "memcpy": {"dst": 0, "size": 2, "argc": 3},
    "memmove": {"dst": 0, "size": 2, "argc": 3},
    "strncpy": {"dst": 0, "size": 2, "argc": 3},
    "memset": {"dst": 0, "size": 2, "argc": 3},
    "snprintf": {"dst": 0, "size": 1, "argc": 2},
    "vsnprintf": {"dst": 0, "size": 1, "argc": 2},
    "fgets": {"dst": 0, "size": 1, "argc": 2},
    "read": {"dst": 1, "size": 2, "argc": 3},
    "recv": {"dst": 1, "size": 2, "argc": 3},
    # connect(int sockfd, const struct sockaddr *addr, socklen_t addrlen)
    "connect": {"dst": 1, "size": 2, "argc": 3},
}


#: Calls whose extra arguments are a varargs list, for ``call_flag_has_varargs``.
#:
#: Deliberately narrower than ``CALL_SEM["format_print"]``, which also carries
#: ``puts`` (not variadic) and ``printIntLine`` (a Juliet harness helper, not
#: libc). This set is the printf family proper.
VARARGS_CALLS = frozenset({"printf", "fprintf", "vprintf", "vfprintf", "sprintf", "snprintf", "vsprintf", "vsnprintf"})


#: Allocators whose argument list is scanned for ``sizeof`` (``alloc_sizeof_state``).
ALLOC_CALLS_FOR_SIZEOF = frozenset({"malloc", "calloc", "realloc", "alloca", "_alloca", "ALLOCA", "new", "new[]"})
