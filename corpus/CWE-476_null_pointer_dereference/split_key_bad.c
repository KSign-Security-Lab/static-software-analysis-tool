#include <string.h>

char *split_key_bad(char *line) {
    char *eq = strchr(line, '=');
    *eq = 0;
    return eq + 1;
}
