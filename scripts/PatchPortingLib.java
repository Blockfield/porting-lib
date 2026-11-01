import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.tree.AbstractInsnNode;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.FieldInsnNode;
import org.objectweb.asm.tree.InsnNode;
import org.objectweb.asm.tree.MethodInsnNode;
import org.objectweb.asm.tree.MethodNode;
import org.objectweb.asm.tree.TypeInsnNode;
import org.objectweb.asm.tree.VarInsnNode;

/**
 * Пустой статический реестр сериализаторов глобальных модификаторов лута: ванила в
 * BuiltInRegistries.validate пишет ERROR "Registry 'porting_lib:global_loot_modifier_serializers'
 * was empty after loading" на старте. Реестр создаётся в PortingLibLoot.&lt;clinit&gt; через
 * PortingLib RegistryBuilder.create() (простой SimpleRegistry + регистрация в корневой карте) и в
 * нашем паке навсегда остаётся пустым: ни один мод не регистрирует сериализаторы и не поставляет
 * GLM-датапак.
 *
 * <p>Патч: создание заменяется на отдельный SimpleRegistry, НЕ зарегистрированный в корневой карте
 * (валидация его не видит). Поле не-null, тип и поведение кода не меняются: entries добавляются
 * теми же Registry.register-вызовами, если мод когда-нибудь их сделает; Fabric-синк не
 * затрагивается (реестр и был несинхронизируемым, MODDED без записей).
 *
 * <p>Условие возврата -- апстрим создаёт реестр лениво или регистрирует запись по умолчанию.
 */
public final class PatchPortingLib {
    private static final String TARGET =
            "io/github/fabricators_of_create/porting_lib/loot/PortingLibLoot";
    private static final String BUILDER_OWNER =
            "io/github/fabricators_of_create/porting_lib/registry/RegistryBuilder";
    private static final String FIELD_KEY = "GLOBAL_LOOT_MODIFIER_SERIALIZERS_KEY";
    private static final String FIELD = "GLOBAL_LOOT_MODIFIER_SERIALIZERS";
    private static final String REGISTRY_KEY = "net/minecraft/class_5321";
    private static final String REGISTRY = "net/minecraft/class_2378";
    private static final String SIMPLE = "net/minecraft/class_2370";
    private static final String LIFECYCLE = "com/mojang/serialization/Lifecycle";

    public static void main(String[] args) throws Exception {
        if (args.length == 1 && args[0].equals("--self-test")) {
            selfTest();
            return;
        }
        if (args.length != 0) {
            throw new IllegalArgumentException("Class bytes are read from stdin");
        }
        System.out.write(patch(System.in.readAllBytes()));
    }

    static byte[] patch(byte[] bytes) {
        ClassNode type = new ClassNode();
        new ClassReader(bytes).accept(type, 0);
        if (!type.name.equals(TARGET)) throw new IllegalStateException("wrong loot class");
        MethodNode clinit =
                type.methods.stream()
                        .filter(m -> m.name.equals("<clinit>"))
                        .findFirst()
                        .orElseThrow(() -> new IllegalStateException("no <clinit>"));
        if (!clinit.tryCatchBlocks.isEmpty()
                || java.util.Arrays.stream(clinit.instructions.toArray())
                        .anyMatch(
                                i ->
                                        i.getOpcode() == Opcodes.JSR
                                                || i instanceof org.objectweb.asm.tree.JumpInsnNode
                                                || i
                                                        instanceof
                                                        org.objectweb.asm.tree.TableSwitchInsnNode
                                                || i
                                                        instanceof
                                                        org.objectweb.asm.tree
                                                                .LookupSwitchInsnNode)) {
            throw new IllegalStateException("<clinit> has branches: frames unsafe");
        }
        int changed = 0;
        for (AbstractInsnNode insn : clinit.instructions.toArray()) {
            if (!(insn instanceof MethodInsnNode call)
                    || call.getOpcode() != Opcodes.INVOKESPECIAL
                    || !call.owner.equals(BUILDER_OWNER)
                    || !call.name.equals("<init>")
                    || !call.desc.equals("(L" + REGISTRY_KEY + ";)V")) continue;
            AbstractInsnNode key = previous(clinit, insn);
            AbstractInsnNode dup = previous(clinit, key);
            AbstractInsnNode created = previous(clinit, dup);
            AbstractInsnNode build = next(clinit, insn);
            AbstractInsnNode store = next(clinit, build);
            if (!(key instanceof FieldInsnNode keyField)
                    || keyField.getOpcode() != Opcodes.GETSTATIC
                    || !keyField.owner.equals(TARGET)
                    || !keyField.name.equals(FIELD_KEY)
                    || !(dup instanceof InsnNode dupInsn)
                    || dupInsn.getOpcode() != Opcodes.DUP
                    || !(created instanceof TypeInsnNode createdInsn)
                    || createdInsn.getOpcode() != Opcodes.NEW
                    || !createdInsn.desc.equals(BUILDER_OWNER)
                    || !(build instanceof MethodInsnNode buildCall)
                    || buildCall.getOpcode() != Opcodes.INVOKEVIRTUAL
                    || !buildCall.owner.equals(BUILDER_OWNER)
                    || !buildCall.name.equals("create")
                    || !buildCall.desc.equals("()L" + REGISTRY + ";")
                    || !(store instanceof FieldInsnNode storeField)
                    || storeField.getOpcode() != Opcodes.PUTSTATIC
                    || !storeField.owner.equals(TARGET)
                    || !storeField.name.equals(FIELD)) {
                throw new IllegalStateException("loot registry site shape changed");
            }
            MethodInsnNode detachedInit =
                    new MethodInsnNode(
                            Opcodes.INVOKESPECIAL,
                            SIMPLE,
                            "<init>",
                            "(L" + REGISTRY_KEY + ";L" + LIFECYCLE + ";Z)V",
                            false);
            clinit.instructions.set(insn, detachedInit);
            clinit.instructions.set(created, new TypeInsnNode(Opcodes.NEW, SIMPLE));
            clinit.instructions.insertBefore(
                    detachedInit,
                    new MethodInsnNode(
                            Opcodes.INVOKESTATIC,
                            LIFECYCLE,
                            "stable",
                            "()L" + LIFECYCLE + ";",
                            false));
            clinit.instructions.insertBefore(detachedInit, new InsnNode(Opcodes.ICONST_0));
            clinit.instructions.remove(build);
            changed++;
        }
        if (changed != 1) {
            throw new IllegalStateException(
                    "expected one loot serializer registry, detached " + changed);
        }
        ClassWriter writer = new ClassWriter(ClassWriter.COMPUTE_MAXS);
        type.accept(writer);
        byte[] patched = writer.toByteArray();
        verify(patched);
        return patched;
    }

    private static AbstractInsnNode previous(MethodNode method, AbstractInsnNode insn) {
        AbstractInsnNode prev = insn.getPrevious();
        while (prev != null && prev.getOpcode() < 0) prev = prev.getPrevious();
        if (prev == null) throw new IllegalStateException("start of <clinit> reached");
        return prev;
    }

    private static AbstractInsnNode next(MethodNode method, AbstractInsnNode insn) {
        AbstractInsnNode next = insn.getNext();
        while (next != null && next.getOpcode() < 0) next = next.getNext();
        if (next == null) throw new IllegalStateException("end of <clinit> reached");
        return next;
    }

    private static void verify(byte[] patched) {
        ClassNode type = new ClassNode();
        new ClassReader(patched).accept(type, 0);
        String initDesc = "(L" + REGISTRY_KEY + ";L" + LIFECYCLE + ";Z)V";
        int builderRefs = 0, builderNews = 0, detachedInits = 0;
        for (MethodNode method : type.methods) {
            for (AbstractInsnNode insn : method.instructions) {
                if (insn instanceof MethodInsnNode call) {
                    if (call.owner.equals(BUILDER_OWNER)) builderRefs++;
                    if (call.owner.equals(SIMPLE)
                            && call.name.equals("<init>")
                            && call.desc.equals(initDesc)) {
                        detachedInits++;
                    }
                }
                if (insn instanceof TypeInsnNode created && created.desc.equals(BUILDER_OWNER)) {
                    builderNews++;
                }
            }
        }
        if (builderRefs != 0 || builderNews != 0 || detachedInits != 1) {
            throw new IllegalStateException(
                    "post-patch shape wrong: builderRefs="
                            + builderRefs
                            + " builderNews="
                            + builderNews
                            + " detachedInits="
                            + detachedInits);
        }
    }

    private static void selfTest() throws Exception {
        ClassNode type = new ClassNode();
        type.version = Opcodes.V21;
        type.access = Opcodes.ACC_PUBLIC;
        type.name = TARGET;
        type.superName = "java/lang/Object";
        type.fields.add(
                new org.objectweb.asm.tree.FieldNode(
                        Opcodes.ACC_PRIVATE | Opcodes.ACC_STATIC,
                        FIELD_KEY,
                        "L" + REGISTRY_KEY + ";",
                        null,
                        null));
        type.fields.add(
                new org.objectweb.asm.tree.FieldNode(
                        Opcodes.ACC_PUBLIC | Opcodes.ACC_STATIC,
                        FIELD,
                        "L" + REGISTRY + ";",
                        null,
                        null));
        MethodNode clinit = new MethodNode(Opcodes.ACC_STATIC, "<clinit>", "()V", null, null);
        clinit.instructions.add(new TypeInsnNode(Opcodes.NEW, BUILDER_OWNER));
        clinit.instructions.add(new InsnNode(Opcodes.DUP));
        clinit.instructions.add(
                new FieldInsnNode(Opcodes.GETSTATIC, TARGET, FIELD_KEY, "L" + REGISTRY_KEY + ";"));
        clinit.instructions.add(
                new MethodInsnNode(
                        Opcodes.INVOKESPECIAL,
                        BUILDER_OWNER,
                        "<init>",
                        "(L" + REGISTRY_KEY + ";)V",
                        false));
        clinit.instructions.add(
                new MethodInsnNode(
                        Opcodes.INVOKEVIRTUAL,
                        BUILDER_OWNER,
                        "create",
                        "()L" + REGISTRY + ";",
                        false));
        clinit.instructions.add(
                new FieldInsnNode(Opcodes.PUTSTATIC, TARGET, FIELD, "L" + REGISTRY + ";"));
        clinit.instructions.add(new InsnNode(Opcodes.RETURN));
        type.methods.add(clinit);
        ClassWriter writer = new ClassWriter(0);
        type.accept(writer);
        byte[] patched = patch(writer.toByteArray());
        ClassNode result = new ClassNode();
        new ClassReader(patched).accept(result, 0);
        if (result.methods.stream()
                .flatMap(m -> java.util.Arrays.stream(m.instructions.toArray()))
                .filter(i -> i instanceof MethodInsnNode c && c.owner.equals(BUILDER_OWNER))
                .findAny()
                .isPresent()) {
            throw new AssertionError("builder refs left");
        }
        try {
            patch(patched);
            throw new AssertionError("duplicate loot patch accepted");
        } catch (IllegalStateException expected) {
        }
        loadTest(patched);
        System.out.println("PortingLib PASS: loot serializers detached; drift guards");
    }

    private static void loadTest(byte[] patched) throws Exception {
        java.util.Map<String, byte[]> stubs = new java.util.HashMap<>();
        stubs.put(REGISTRY_KEY, stubClass(REGISTRY_KEY, "java/lang/Object", null));
        stubs.put(LIFECYCLE, stubClass(LIFECYCLE, "java/lang/Object", "stable"));
        stubs.put(REGISTRY, stubClass(REGISTRY, "java/lang/Object", null));
        stubs.put(
                SIMPLE,
                stubInit(SIMPLE, REGISTRY, "(L" + REGISTRY_KEY + ";L" + LIFECYCLE + ";Z)V"));
        ClassLoader loader =
                new ClassLoader(PatchPortingLib.class.getClassLoader()) {
                    @Override
                    protected Class<?> findClass(String name) throws ClassNotFoundException {
                        String internal = name.replace('.', '/');
                        byte[] bytes = internal.equals(TARGET) ? patched : stubs.get(internal);
                        if (bytes == null) throw new ClassNotFoundException(name);
                        return defineClass(name, bytes, 0, bytes.length);
                    }
                };
        Class<?> loot = Class.forName(TARGET.replace('/', '.'), true, loader);
        Object registry = loot.getField(FIELD).get(null);
        Class<?> simple = Class.forName(SIMPLE.replace('/', '.'), false, loader);
        if (!simple.isInstance(registry)) {
            throw new AssertionError("field is not a detached SimpleRegistry");
        }
    }

    private static byte[] stubClass(String name, String superName, String factory) {
        ClassNode type = new ClassNode();
        type.version = Opcodes.V21;
        type.access = Opcodes.ACC_PUBLIC;
        type.name = name;
        type.superName = superName;
        type.methods.add(defaultConstructor(superName));
        if (factory != null) {
            MethodNode make =
                    new MethodNode(
                            Opcodes.ACC_PUBLIC | Opcodes.ACC_STATIC,
                            factory,
                            "()L" + name + ";",
                            null,
                            null);
            make.instructions.add(new TypeInsnNode(Opcodes.NEW, name));
            make.instructions.add(new InsnNode(Opcodes.DUP));
            make.instructions.add(
                    new MethodInsnNode(Opcodes.INVOKESPECIAL, name, "<init>", "()V", false));
            make.instructions.add(new InsnNode(Opcodes.ARETURN));
            type.methods.add(make);
        }
        ClassWriter writer = new ClassWriter(ClassWriter.COMPUTE_MAXS);
        type.accept(writer);
        return writer.toByteArray();
    }

    private static byte[] stubInit(String name, String superName, String desc) {
        ClassNode type = new ClassNode();
        type.version = Opcodes.V21;
        type.access = Opcodes.ACC_PUBLIC;
        type.name = name;
        type.superName = superName;
        type.methods.add(defaultConstructor(superName));
        MethodNode init = new MethodNode(Opcodes.ACC_PUBLIC, "<init>", desc, null, null);
        init.instructions.add(new VarInsnNode(Opcodes.ALOAD, 0));
        init.instructions.add(
                new MethodInsnNode(Opcodes.INVOKESPECIAL, superName, "<init>", "()V", false));
        init.instructions.add(new InsnNode(Opcodes.RETURN));
        type.methods.add(init);
        ClassWriter writer = new ClassWriter(ClassWriter.COMPUTE_MAXS);
        type.accept(writer);
        return writer.toByteArray();
    }

    private static MethodNode defaultConstructor(String superName) {
        MethodNode init = new MethodNode(Opcodes.ACC_PUBLIC, "<init>", "()V", null, null);
        init.instructions.add(new VarInsnNode(Opcodes.ALOAD, 0));
        init.instructions.add(
                new MethodInsnNode(Opcodes.INVOKESPECIAL, superName, "<init>", "()V", false));
        init.instructions.add(new InsnNode(Opcodes.RETURN));
        return init;
    }
}
