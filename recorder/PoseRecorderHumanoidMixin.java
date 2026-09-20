package @MIXIN_PACKAGE@;

import @PACKAGE@.PoseRecorder;
import net.minecraft.client.model.HumanoidModel;
import net.minecraft.client.renderer.entity.state.HumanoidRenderState;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/** Model viewer pose recorder: reads the finished pose after every other mod has had its say. Changes nothing. */
@Mixin(value = HumanoidModel.class, priority = 5000)
abstract class PoseRecorderHumanoidMixin {
    @Inject(method = "setupAnim(Lnet/minecraft/client/renderer/entity/state/HumanoidRenderState;)V", at = @At("TAIL"), require = 0)
    private void modelviewer$record(HumanoidRenderState state, CallbackInfo ci) {
        PoseRecorder.sampleParts((HumanoidModel<?>) (Object) this, state);
    }
}
