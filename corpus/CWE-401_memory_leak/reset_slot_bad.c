#include <stdlib.h>

void reset_slot_bad(struct slot *s, int n) {
    /* the previous buffer is dropped without being freed */
    s->buf = malloc((size_t)n);
    s->len = n;
}
