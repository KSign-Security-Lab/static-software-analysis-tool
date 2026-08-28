#include <string.h>

void terminate_at_fixed(char *buf, size_t cap, const char *in) {
    /* the last writable index is cap - 1 */
    size_t n = strlen(in);
    if (n > cap - 1) n = cap - 1;
    memcpy(buf, in, n);
    buf[n] = 0;
}
