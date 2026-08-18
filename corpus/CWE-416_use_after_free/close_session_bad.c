#include <stdlib.h>

void close_session_bad(struct session *s) {
    /* the object is read after it has been handed back to the allocator */
    free(s);
    log_id(s->id);
}
