#include <string.h>

char *split_key_fixed(char *line) {
    char *eq = strchr(line, '=');
    if (eq == NULL) return NULL;
    *eq = 0;
    return eq + 1;
}
