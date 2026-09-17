#include <stdlib.h>

void close_session_fixed(struct session *s) {
    int id = s->id;
    free(s);
    log_id(id);
}
