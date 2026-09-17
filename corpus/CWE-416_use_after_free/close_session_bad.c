#include <stdlib.h>

void close_session_bad(struct session *s) {
    free(s);
    log_id(s->id);
}
