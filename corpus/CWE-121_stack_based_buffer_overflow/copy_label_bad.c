#include <string.h>

void copy_label_bad(const char *in) {
    char label[16];
    strcpy(label, in);
    use(label);
}
