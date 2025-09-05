// C Standard Library functions
const cStdLibFunctions: string[] = [
  "memset", // <string.h>
  "memcpy", // <string.h>
  "memmove", // <string.h>
  "strlen", // <string.h>
  "strcpy", // <string.h>
  "wcscpy", // <wchar.h>
  "wcslen", // <wchar.h>
  "atoi", // <stdlib.h>
  "fgets", // <stdio.h>
  "fscanf", // <stdio.h>
  "calloc", // <stdlib.h>
  "free", // <stdlib.h>
  "exit", // <stdlib.h>
  "srand", // <stdlib.h>
  "time", // <time.h>
];

// POSIX Networking functions
const posixNetworkingFunctions: string[] = [
  "socket", // <sys/socket.h>
  "bind", // <sys/socket.h>
  "listen", // <sys/socket.h>
  "accept", // <sys/socket.h>
  "connect", // <sys/socket.h>
  "recv", // <sys/socket.h>
  "htons", // <arpa/inet.h>
  "inet_addr", // <arpa/inet.h> (obsolete; prefer inet_pton/getaddrinfo)
  "close", // <unistd.h>
];

// C++ STL container methods
const cppStlMethods: string[] = [
  "insert", // e.g., std::vector, std::list, std::set, etc.
  "push_back", // e.g., std::vector, std::deque, std::list
  "end", // returns iterator past last element
  "back", // access last element in sequence containers
];

// Combined list, if a single array is preferred
const standardLibCalls: string[] = [
  // C Standard Library
  "malloc",
  "memset",
  "memcpy",
  "memmove",
  "strlen",
  "strcpy",
  "wcscpy",
  "wcslen",
  "atoi",
  "fgets",
  "fscanf",
  "calloc",
  "free",
  "exit",
  "srand",
  "time",
  // POSIX Networking
  "socket",
  "bind",
  "listen",
  "accept",
  "connect",
  "recv",
  "htons",
  "inet_addr",
  "close",
  // C++ STL
  "insert",
  "push_back",
  "end",
  "back",
];

export const STANDARD_LIB_CALLS = new Set<string>([...cppStlMethods, ...cStdLibFunctions, ...posixNetworkingFunctions, ...standardLibCalls]);
