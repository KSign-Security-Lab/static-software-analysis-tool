#include <string.h>

/* A function-like macro round an unbounded sink. Joern inlines the expansion
   under the use site with the arguments already substituted, so the copy is
   reachable -- but the node is named after the macro until it is folded. */
#define COPY_URL(dst, src) strcpy(dst, src)

void set_firmware_url(char *dst, const char *src) {
    COPY_URL(dst, src);
}
