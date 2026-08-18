#include <stdlib.h>

void close_session_fixed(struct session *s) {
    /* everything needed is taken before the free */
    int id = s->id;
    free(s);
    log_id(id);
}
