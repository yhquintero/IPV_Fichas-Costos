# IPV Fichas y Costos — ProGuard rules
-keepattributes *Annotation*
-keepattributes Signature
-keepattributes InnerClasses

# Keep JSON parsing
-keep class org.json.** { *; }
-dontwarn org.json.**

# Keep application classes
-keep class cu.ipvcostos.app.** { *; }
