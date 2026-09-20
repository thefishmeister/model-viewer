package @MIXIN_PACKAGE@;

import com.mojang.blaze3d.vertex.PoseStack;
import @PACKAGE@.PoseRecorder;
import net.minecraft.client.renderer.SubmitNodeCollector;
import net.minecraft.client.renderer.entity.layers.ItemInHandLayer;
import net.minecraft.client.renderer.entity.state.ArmedEntityRenderState;
import net.minecraft.client.renderer.entity.state.HumanoidRenderState;
import net.minecraft.client.renderer.item.ItemStackRenderState;
import net.minecraft.world.entity.HumanoidArm;
import net.minecraft.world.item.ItemStack;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/** Model viewer pose recorder: reads where the held item ends up, after every other mod's hand transforms. Changes nothing. */
@Mixin(value = ItemInHandLayer.class, priority = 5000)
abstract class PoseRecorderItemMixin {
    @Inject(method = "submitArmWithItem", at = @At("HEAD"), require = 0)
    private void modelviewer$enter(ArmedEntityRenderState state, ItemStackRenderState item, ItemStack stack,
                                   HumanoidArm arm, PoseStack pose, SubmitNodeCollector collector, int light, CallbackInfo ci) {
        PoseRecorder.enterItemLayer(pose);
    }

    @Inject(method = "submitArmWithItem", at = @At(value = "INVOKE",
            target = "Lnet/minecraft/client/renderer/item/ItemStackRenderState;submit(Lcom/mojang/blaze3d/vertex/PoseStack;Lnet/minecraft/client/renderer/SubmitNodeCollector;III)V"), require = 0)
    private void modelviewer$item(ArmedEntityRenderState state, ItemStackRenderState item, ItemStack stack,
                                  HumanoidArm arm, PoseStack pose, SubmitNodeCollector collector, int light, CallbackInfo ci) {
        if (state instanceof HumanoidRenderState humanoid) PoseRecorder.sampleItem(humanoid, arm, stack, pose);
    }
}
