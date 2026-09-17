#include <stdio.h>

void extract_entry_fixed(const char *entry, const char *data) {
    if (entry[0] == '/' || strstr(entry, "..") != NULL) return;
    char out[512];
    snprintf(out, sizeof(out), "./unpack/%s", entry);
    FILE *f = fopen(out, "wb");
    if (f != NULL) { fputs(data, f); fclose(f); }
}
