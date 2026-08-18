#include <stdlib.h>

void reset_slot_fixed(struct slot *s, int n) {
    char *buf = malloc((size_t)n);
    if (buf == NULL) return;
    free(s->buf);
    s->buf = buf;
    s->len = n;
}
